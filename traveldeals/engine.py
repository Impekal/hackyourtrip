"""The deal engine: turns raw provider offers into ranked, annotated
TripOptions for one RoutePreference.

Pipeline per route: gather offers per requested mode -> build combos where
requested -> filter by hard constraints (budget, max duration, low-cost
allowed) -> score & rank by the user's priority -> attach smart
recommendations (later-departure savings, baggage savings, currency info,
price-drop/error-fare flags) -> return the top N.
"""
from __future__ import annotations

from datetime import date, datetime

from traveldeals.currency import convert, get_rates_per_eur
from traveldeals.models import (Mode, Offer, Priority, RoutePreference,
                                 TripOption)
from traveldeals.pricehistory import PriceHistory
from traveldeals.providers.base import Provider

# best_value weighting: price matters more than duration by default because
# the brief frames "budget" as the primary constraint and duration as a
# secondary preference ("wie viele Stunden ich verbringen möchte"). Tune here
# if that balance should shift.
BEST_VALUE_PRICE_WEIGHT = 0.6
BEST_VALUE_DURATION_WEIGHT = 0.4

# below this fraction of the median observed price, flag a price drop; below
# this fraction of the historical minimum, flag a likely error fare.
PRICE_DROP_RATIO = 0.85
ERROR_FARE_RATIO = 0.5

# a checked-bag fee worth at least this fraction of the total price is worth
# surfacing as a "go carry-on-only" recommendation.
BAGGAGE_SAVINGS_THRESHOLD = 0.15

_HOTEL_COMBO_TRANSPORT_MODE = {
    Mode.FLIGHT_HOTEL: Mode.FLIGHT,
    Mode.TRAIN_HOTEL: Mode.TRAIN,
    Mode.BUS_HOTEL: Mode.BUS,
}


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
            elif mode == Mode.TRAIN_OR_BUS:
                for offer in pool(Mode.TRAIN) + pool(Mode.BUS):
                    candidates.append(self._single_offer_option(Mode.TRAIN_OR_BUS, offer))

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
        return BEST_VALUE_PRICE_WEIGHT * price_norm + BEST_VALUE_DURATION_WEIGHT * duration_norm

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
        same_day_later = [
            o for o in pool
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
        if not self._rates_per_eur or option.mode not in (Mode.FLIGHT, Mode.FLIGHT_HOTEL, Mode.HOTEL):
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
