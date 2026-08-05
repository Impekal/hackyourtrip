"""The deal engine: turns raw provider offers into ranked, annotated
TripOptions for one RoutePreference.

Pipeline per route: gather offers per requested mode -> build combos where
requested -> filter by hard constraints (budget, max duration, low-cost,
hotel amenities, transport comfort) -> score & rank by the user's priority
(best_value blends in a comfort score, not just price/duration) -> attach
smart recommendations (later-departure savings, baggage savings, currency
info, price-drop/error-fare flags) -> return the top N.
"""
from __future__ import annotations

from datetime import date, datetime

from traveldeals.currency import convert, get_rates_per_eur
from traveldeals.models import (OR_COMBO_MODES, HotelPref, Mode, Offer,
                                 Priority, RoutePreference, TransportPref,
                                 TripOption)
from traveldeals.pricehistory import PriceHistory
from traveldeals.providers.base import Provider

# best_value weighting: price still matters most, but a comfort score (hotel
# amenities / transport comfort - see comfort_score() below) now factors in
# too, since "bestes Verhaeltnis" should mean more than just price vs time.
# Tune here if that balance should shift.
BEST_VALUE_PRICE_WEIGHT = 0.5
BEST_VALUE_DURATION_WEIGHT = 0.25
BEST_VALUE_COMFORT_WEIGHT = 0.25

# below this fraction of the median observed price, flag a price drop; below
# this fraction of the historical minimum, flag a likely error fare.
PRICE_DROP_RATIO = 0.85
ERROR_FARE_RATIO = 0.5

# a checked-bag fee worth at least this fraction of the total price is worth
# surfacing as a "go carry-on-only" recommendation.
BAGGAGE_SAVINGS_THRESHOLD = 0.15

# seat-pitch ranges used to normalize legroom_cm into a 0..1 comfort
# component - flight economy seats are simply tighter than train/bus seats,
# so each mode gets its own scale rather than one shared range.
LEGROOM_RANGE_BY_MODE = {
    Mode.FLIGHT: (66.0, 96.0),
    Mode.TRAIN: (85.0, 120.0),
    Mode.BUS: (70.0, 100.0),
}

_HOTEL_COMBO_TRANSPORT_MODE = {
    Mode.FLIGHT_HOTEL: Mode.FLIGHT,
    Mode.TRAIN_HOTEL: Mode.TRAIN,
    Mode.BUS_HOTEL: Mode.BUS,
}


def hotel_comfort_score(offer: Offer) -> float:
    """0..1, higher is better: blends stars, user rating, amenity coverage,
    and closeness - equal-weighted since there's no principled reason to
    prefer one over another without user-specific data."""
    stars_norm = ((offer.stars or 3) - 1) / 4
    rating_norm = (offer.rating or 7.0) / 10
    amenities = [offer.wifi, offer.breakfast_included, offer.free_cancellation,
                 offer.parking, offer.air_conditioning, offer.pets_allowed, offer.pool_or_fitness]
    amenity_norm = sum(1 for a in amenities if a) / len(amenities)
    distance_norm = 1 - min(offer.distance_km or 3.0, 10) / 10
    return (stars_norm + rating_norm + amenity_norm + distance_norm) / 4


def transport_comfort_score(offer: Offer) -> float:
    """0..1, higher is better: legroom, onboard wifi/power, directness,
    punctuality - equal-weighted, same rationale as hotel_comfort_score."""
    lo, hi = LEGROOM_RANGE_BY_MODE.get(offer.mode, (70.0, 100.0))
    legroom_norm = min(max(((offer.legroom_cm or lo) - lo) / (hi - lo), 0), 1)
    direct_bonus = {0: 1.0, 1: 0.5}.get(offer.stops, 0.0)
    punctuality_norm = (offer.punctuality_pct or 80.0) / 100
    parts = [legroom_norm, float(offer.wifi_onboard), float(offer.power_outlets), direct_bonus, punctuality_norm]
    return sum(parts) / len(parts)


def comfort_score(option: TripOption) -> float:
    scores = []
    for o in option.offers:
        if o.mode == Mode.HOTEL:
            scores.append(hotel_comfort_score(o))
        elif o.mode in (Mode.FLIGHT, Mode.TRAIN, Mode.BUS):
            scores.append(transport_comfort_score(o))
    return sum(scores) / len(scores) if scores else 0.5


def _meets_hotel_constraints(offer: Offer, pref: HotelPref) -> bool:
    if pref.min_stars is not None and (offer.stars or 0) < pref.min_stars:
        return False
    if pref.min_rating is not None and (offer.rating or 0) < pref.min_rating:
        return False
    if pref.max_distance_km is not None and (offer.distance_km or 0) > pref.max_distance_km:
        return False
    if pref.require_wifi and not offer.wifi:
        return False
    if pref.require_breakfast and not offer.breakfast_included:
        return False
    if pref.require_free_cancellation and not offer.free_cancellation:
        return False
    if pref.require_parking and not offer.parking:
        return False
    if pref.require_air_conditioning and not offer.air_conditioning:
        return False
    if pref.require_pets_allowed and not offer.pets_allowed:
        return False
    if pref.require_pool_or_fitness and not offer.pool_or_fitness:
        return False
    return True


def _minutes_since_midnight(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")[:2]
    return int(hours) * 60 + int(minutes)


def _circular_minutes_diff(a: int, b: int) -> int:
    """Distance between two times-of-day on a 24h clock, wrapping at
    midnight - so a 23:30 preference with 90min flex still matches 00:30."""
    diff = abs(a - b) % 1440
    return min(diff, 1440 - diff)


def _meets_transport_constraints(offer: Offer, pref: TransportPref) -> bool:
    if pref.direct_only and offer.stops > 0:
        return False
    if pref.require_wifi_onboard and not offer.wifi_onboard:
        return False
    if pref.require_power_outlets and not offer.power_outlets:
        return False
    if pref.min_punctuality_pct is not None and (offer.punctuality_pct or 0) < pref.min_punctuality_pct:
        return False
    if pref.preferred_depart_time is not None:
        offer_minutes = _minutes_since_midnight(offer.depart_time[11:16])
        preferred_minutes = _minutes_since_midnight(pref.preferred_depart_time)
        if _circular_minutes_diff(offer_minutes, preferred_minutes) > pref.depart_time_flex_minutes:
            return False
    return True


class DealEngine:
    def __init__(self, providers: dict[Mode, Provider], price_history: PriceHistory,
                 as_of: date | None = None, use_live_currency: bool = True):
        self.providers = providers
        self.price_history = price_history
        self.as_of = as_of or date.today()
        self._rates_per_eur = get_rates_per_eur() if use_live_currency else None

    def search(self, route: RoutePreference, top_n: int = 5) -> list[TripOption]:
        candidates: list[TripOption] = []
        offer_pools: dict[Mode, list[Offer]] = {}

        def pool(mode: Mode) -> list[Offer]:
            if mode not in offer_pools:
                provider = self.providers.get(mode)
                offer_pools[mode] = provider.search(route) if provider else []
            return offer_pools[mode]

        for mode in route.modes:
            if mode in (Mode.FLIGHT, Mode.TRAIN, Mode.BUS, Mode.HOTEL):
                for offer in pool(mode):
                    candidates.append(self._single_offer_option(mode, offer))
            elif mode in _HOTEL_COMBO_TRANSPORT_MODE:
                transport_mode = _HOTEL_COMBO_TRANSPORT_MODE[mode]
                candidates.extend(self._combo_options(mode, pool(transport_mode), pool(Mode.HOTEL)))
            elif mode in OR_COMBO_MODES:
                mode_a, mode_b = OR_COMBO_MODES[mode]
                for offer in pool(mode_a) + pool(mode_b):
                    candidates.append(self._single_offer_option(mode, offer))

        candidates = [c for c in candidates if self._meets_hard_constraints(c, route)]
        for c in candidates:
            c.score = self._score(c, route.priority, candidates)
        candidates.sort(key=lambda c: c.score)
        top = candidates[:top_n]

        for option in top:
            self._annotate(option, route, offer_pools)

        return top

    # -- building candidates -------------------------------------------------

    def _single_offer_option(self, mode: Mode, offer: Offer) -> TripOption:
        return TripOption(mode=mode, offers=[offer], total_price=offer.price,
                           currency=offer.currency, total_duration_hours=offer.duration_hours,
                           score=0.0)

    def _combo_options(self, combo_mode: Mode, transport_offers: list[Offer],
                        hotel_offers: list[Offer]) -> list[TripOption]:
        options = []
        hotels_by_checkin = {}
        for h in hotel_offers:
            hotels_by_checkin.setdefault(h.depart_time[:10], []).append(h)
        for t in transport_offers:
            day = t.depart_time[:10]
            same_day_hotels = hotels_by_checkin.get(day, [])
            if not same_day_hotels:
                continue
            cheapest_hotel = min(same_day_hotels, key=lambda h: h.price)
            options.append(TripOption(
                mode=combo_mode, offers=[t, cheapest_hotel],
                total_price=round(t.price + cheapest_hotel.price, 2),
                currency=t.currency, total_duration_hours=t.duration_hours, score=0.0,
            ))
        return options

    # -- filtering & scoring --------------------------------------------------

    def _meets_hard_constraints(self, option: TripOption, route: RoutePreference) -> bool:
        if route.budget is not None and option.total_price > route.budget:
            return False
        if route.max_duration_hours is not None and option.total_duration_hours > route.max_duration_hours:
            # hotel-only trips have no transport duration constraint
            if option.mode != Mode.HOTEL:
                return False
        if not route.low_cost_airlines_ok and any(o.is_low_cost for o in option.offers):
            return False
        for offer in option.offers:
            if offer.mode == Mode.HOTEL and not _meets_hotel_constraints(offer, route.hotel):
                return False
            if offer.mode in (Mode.FLIGHT, Mode.TRAIN, Mode.BUS) and not _meets_transport_constraints(offer, route.transport):
                return False
        return True

    def _score(self, option: TripOption, priority: Priority, all_candidates: list[TripOption]) -> float:
        if priority == Priority.CHEAPEST:
            return option.total_price
        if priority == Priority.FASTEST:
            return option.total_duration_hours
        prices = [c.total_price for c in all_candidates]
        durations = [c.total_duration_hours for c in all_candidates]
        price_norm = _normalize(option.total_price, prices)
        duration_norm = _normalize(option.total_duration_hours, durations)
        discomfort_norm = 1 - comfort_score(option)
        return (BEST_VALUE_PRICE_WEIGHT * price_norm
                + BEST_VALUE_DURATION_WEIGHT * duration_norm
                + BEST_VALUE_COMFORT_WEIGHT * discomfort_norm)

    # -- recommendations -------------------------------------------------------

    def _annotate(self, option: TripOption, route: RoutePreference, offer_pools: dict[Mode, list[Offer]]) -> None:
        transport_offer = option.offers[0]
        same_mode_pool = offer_pools.get(transport_offer.mode, [])

        self._add_later_departure_hint(option, transport_offer, same_mode_pool, route)
        self._add_baggage_hint(option, transport_offer, route)
        self._add_currency_info(option, route)

        route_key = f"{route.origin}->{route.destination}:{option.mode.value}"
        is_drop, is_error = self.price_history.is_notable_low(route_key, transport_offer.mode.value, option.total_price,
                                                                PRICE_DROP_RATIO, ERROR_FARE_RATIO)
        if is_error:
            option.is_error_fare = True
            option.recommendations.insert(0, "🔥 Möglicher Fehlerpreis – deutlich unter dem bisherigen Tiefstpreis!")
        elif is_drop:
            option.is_price_drop = True
            option.recommendations.insert(0, "📉 Preis ist gefallen gegenüber dem bisherigen Median.")
        self.price_history.record(route_key, transport_offer.mode.value, option.total_price, option.currency, self.as_of)

    def _add_later_departure_hint(self, option: TripOption, offer: Offer, pool: list[Offer],
                                   route: RoutePreference) -> None:
        if offer.mode not in (Mode.FLIGHT, Mode.TRAIN, Mode.BUS):
            return
        # Only compare against offers that also satisfy the route's own
        # transport constraints (esp. the depart-time window) - otherwise
        # this could suggest a time the user already said doesn't work for
        # them, which would contradict their own stated flexibility.
        eligible_pool = [o for o in pool if _meets_transport_constraints(o, route.transport)]
        same_day_later = [
            o for o in eligible_pool
            if o.depart_time[:10] == offer.depart_time[:10]
            and o.depart_time > offer.depart_time
            and o.price < offer.price
        ]
        if not same_day_later:
            return
        best = min(same_day_later, key=lambda o: o.price)
        hours_later = (datetime.fromisoformat(best.depart_time) - datetime.fromisoformat(offer.depart_time)).seconds / 3600
        savings = round(offer.price - best.price, 2)
        if savings > 0:
            option.recommendations.append(
                f"🕐 {round(hours_later, 1)}h später ({best.depart_time[11:16]} statt {offer.depart_time[11:16]}) "
                f"spart {savings} {offer.currency}."
            )

    def _add_baggage_hint(self, option: TripOption, offer: Offer, route: RoutePreference) -> None:
        if offer.checked_bag_fee <= 0:
            return
        bags = max(route.baggage.checked_bags, 1)
        savings = round(offer.checked_bag_fee * bags, 2)
        if savings / option.total_price >= BAGGAGE_SAVINGS_THRESHOLD:
            option.recommendations.append(
                f"🎒 Nur Handgepäck statt {bags}x Koffer ({route.baggage.checked_bag_kg}kg) spart {savings} {offer.currency}."
            )

    def _add_currency_info(self, option: TripOption, route: RoutePreference) -> None:
        involves_flight_or_hotel = any(o.mode in (Mode.FLIGHT, Mode.HOTEL) for o in option.offers)
        if not self._rates_per_eur or not involves_flight_or_hotel:
            return
        others = [c for c in ("USD", "GBP") if c != option.currency]
        equivalents = [f"{convert(option.total_price, option.currency, c, self._rates_per_eur)} {c}" for c in others]
        if equivalents:
            option.recommendations.append(
                "💱 Entspricht ca. " + " / ".join(equivalents) +
                " – ob eine Buchung in anderer Landeswährung günstiger ist, prüft v1 noch nicht automatisch."
            )


def _normalize(value: float, all_values: list[float]) -> float:
    lo, hi = min(all_values), max(all_values)
    if hi == lo:
        return 0.0
    return (value - lo) / (hi - lo)
