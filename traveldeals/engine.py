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
from traveldeals.models import (MEAL_PLAN_TIERS, MIXED_RETURN_MODES, OR_COMBO_MODES,
                                 TRANSPORT_MODES, HotelPref, Mode, Offer,
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

# "Deals only" without any price history: an option counts as a deal when
# it's at least this much below the median of the same search. Needs a
# minimum number of candidates for a median to mean anything at all.
BELOW_MEDIAN_DEAL_RATIO = 0.85
MIN_CANDIDATES_FOR_MEDIAN_DEAL = 4

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


# Every boolean hotel amenity flag on Offer, used both for the comfort score
# below (coverage ratio) and left for callers who want the full list.
HOTEL_AMENITY_FIELDS = [
    "wifi", "free_cancellation", "parking", "air_conditioning", "pets_allowed",
    "pool", "gym", "spa", "restaurant", "bar", "room_service", "front_desk_24h",
    "business_facilities", "laundry_service", "elevator", "balcony_or_terrace",
    "kitchen", "beachfront", "disabled_access", "ev_charging", "bicycle_rental",
    "babysitting", "sauna", "hot_tub", "non_smoking", "family_rooms", "airport_shuttle",
]


def hotel_comfort_score(offer: Offer) -> float:
    """0..1, higher is better: blends stars, user rating, amenity coverage,
    meal plan, and closeness - equal-weighted since there's no principled
    reason to prefer one over another without user-specific data.

    Unknown values fall back to the middle of their range, not to the worst
    end. A source that stays silent about the breakfast must not thereby
    make the hotel look bad; that would quietly rank real offers below
    invented ones, which is precisely backwards.
    """
    stars_norm = ((offer.stars or 3) - 1) / 4
    rating_norm = (offer.rating or 7.0) / 10
    # Only count amenities that are actually known. Scoring `None` as absent
    # would punish a source for its silence.
    known = [f for f in HOTEL_AMENITY_FIELDS if getattr(offer, f) is not None]
    amenity_norm = (sum(1 for f in known if getattr(offer, f)) / len(known)) if known else 0.5
    distance_norm = 1 - min(offer.distance_km or 3.0, 10) / 10
    meal_plan_norm = (MEAL_PLAN_TIERS.index(offer.meal_plan) / (len(MEAL_PLAN_TIERS) - 1)
                      if offer.meal_plan in MEAL_PLAN_TIERS else 0.5)
    return (stars_norm + rating_norm + amenity_norm + distance_norm + meal_plan_norm) / 5


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


# Maps each HotelPref.require_X flag to the Offer field it checks - covers
# every boolean amenity below the core stars/rating/distance/type/meal-plan
# filters, so adding a new amenity is a one-line addition to this dict
# instead of another if-statement.
_HOTEL_AMENITY_REQUIREMENTS = {
    "require_wifi": "wifi",
    "require_free_cancellation": "free_cancellation",
    "require_parking": "parking",
    "require_air_conditioning": "air_conditioning",
    "require_pets_allowed": "pets_allowed",
    "require_pool": "pool",
    "require_gym": "gym",
    "require_spa": "spa",
    "require_restaurant": "restaurant",
    "require_bar": "bar",
    "require_room_service": "room_service",
    "require_24h_front_desk": "front_desk_24h",
    "require_business_facilities": "business_facilities",
    "require_laundry_service": "laundry_service",
    "require_elevator": "elevator",
    "require_balcony_or_terrace": "balcony_or_terrace",
    "require_kitchen": "kitchen",
    "require_beachfront": "beachfront",
    "require_disabled_access": "disabled_access",
    "require_ev_charging": "ev_charging",
    "require_bicycle_rental": "bicycle_rental",
    "require_babysitting": "babysitting",
    "require_sauna": "sauna",
    "require_hot_tub": "hot_tub",
    "require_non_smoking": "non_smoking",
    "require_family_rooms": "family_rooms",
    "require_airport_shuttle": "airport_shuttle",
}


def _meets_hotel_constraints(offer: Offer, pref: HotelPref) -> bool:
    """Does this hotel meet the stated requirements?

    `None` means "this source doesn't say", and that must not act like a
    "no" - the same distinction `price_known` and `d_ticket_covered` draw.
    The mock provider fills every field, so nothing changes for it. A real
    source knows some things and not others: LiteAPI states the board type
    and whether a rate is refundable, but says nothing about pets or air
    conditioning. Letting that silence exclude the hotel would empty the
    list for anyone who ticks a single box - and it would look exactly like
    "there are no hotels there", which is a different, wrong answer.
    """
    if pref.min_stars is not None and offer.stars is not None and offer.stars < pref.min_stars:
        return False
    if pref.min_rating is not None and offer.rating is not None and offer.rating < pref.min_rating:
        return False
    if (pref.max_distance_km is not None and offer.distance_km is not None
            and offer.distance_km > pref.max_distance_km):
        return False
    if (pref.property_types and offer.property_type is not None
            and offer.property_type not in pref.property_types):
        return False
    if (pref.min_meal_plan is not None and offer.meal_plan is not None
            and MEAL_PLAN_TIERS.index(offer.meal_plan)
            < MEAL_PLAN_TIERS.index(pref.min_meal_plan)):
        return False
    for pref_flag, offer_field in _HOTEL_AMENITY_REQUIREMENTS.items():
        if getattr(pref, pref_flag) and getattr(offer, offer_field) is False:
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

    # Raised from 5: the providers now return dozens of offers per search,
    # so a tight cap was hiding most of what was actually found.
    def search(self, route: RoutePreference, top_n: int = 25) -> list[TripOption]:
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
            elif mode is Mode.MIXED_RETURN:
                for m in MIXED_RETURN_MODES:
                    pool(m)  # fill offer_pools so the pairing can read them
                candidates.extend(self._mixed_return_options(offer_pools))

        candidates = [c for c in candidates if self._meets_hard_constraints(c, route)]
        _flag_below_median(candidates)
        for c in candidates:
            c.score = self._score(c, route.priority, candidates, route)
        # Options with no known price (timetable sources like Transitous) sort
        # behind every priced one whatever the priority is: their total_price
        # of 0.0 is a placeholder, and letting it compete would park them at
        # the very top of a "cheapest" search as though they were free.
        candidates.sort(key=lambda c: (c.has_unknown_price, c.score))

        if route.deals_only:
            # is_error_fare/is_price_drop come from the price history and are
            # only set during _annotate, so annotate the whole (already
            # ranked) list first and filter afterwards - otherwise
            # "only deals" could only ever see the below-median signal.
            for option in candidates:
                self._annotate(option, route, offer_pools)
            return [c for c in candidates if c.is_deal][:top_n]

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

    def _mixed_return_options(self, pools: dict[Mode, list[Offer]]) -> list[TripOption]:
        """Out one way, back another - the pairing no portal sells.

        Every outbound is paired with the best return *per mode* rather than
        with every return: all-against-all would produce thousands of options
        differing only in the return, and the cheapest return of a mode
        dominates the rest anyway.

        A mode whose returns carry no price still contributes one
        representative, so a timetable-only mode (Bahn) is not simply missing
        from the comparison - it appears with its price honestly unknown.

        Mirrors pairLegs() in docs/app.js.
        """
        # One-way legs only: an offer that already books its own return is a
        # round trip, not half of a mixed one.
        def one_way(offers: list[Offer]) -> list[Offer]:
            return [o for o in offers if not o.return_depart_time]

        best_return: dict[Mode, Offer] = {}
        for mode in MIXED_RETURN_MODES:
            for candidate in one_way(pools.get(mode, [])):
                current = best_return.get(mode)
                if current is None:
                    best_return[mode] = candidate
                elif not current.price_known and candidate.price_known:
                    best_return[mode] = candidate
                elif (current.price_known and candidate.price_known
                        and candidate.price < current.price):
                    best_return[mode] = candidate

        options: list[TripOption] = []
        for mode in MIXED_RETURN_MODES:
            for out in one_way(pools.get(mode, [])):
                for back in best_return.values():
                    # A return leaving before the outbound is not a trip.
                    if back.depart_time <= out.depart_time:
                        continue
                    options.append(TripOption(
                        mode=Mode.MIXED_RETURN, offers=[out, back],
                        total_price=round(out.price + back.price, 2),
                        currency=out.currency,
                        total_duration_hours=round(
                            out.duration_hours + back.duration_hours, 2),
                        score=0.0,
                    ))
        return options

    # -- filtering & scoring --------------------------------------------------

    @staticmethod
    def _within_duration_limits(option: TripOption, route: RoutePreference) -> bool:
        """Max travel time, per direction when a return leg exists.

        The way out and the way back rarely deserve the same limit - a
        12-hour night bus there can be fine while the same on the way back,
        before work, is not. Without a return leg this is exactly the old
        single check against the option's duration.

        A return leg whose duration the source doesn't state is not a
        violation: unknown is unknown, not "too long".
        """
        offers = option.offers
        first = offers[0] if offers else None
        back_hours = None
        if len(offers) == 2 and all(o.mode in TRANSPORT_MODES for o in offers):
            back_hours = offers[1].duration_hours
        elif first is not None:
            back_hours = first.return_duration_hours

        if back_hours is None:
            return not (route.max_duration_hours is not None
                        and option.total_duration_hours > route.max_duration_hours)
        if route.max_duration_hours is not None and first.duration_hours > route.max_duration_hours:
            return False
        if (route.max_duration_return_hours is not None
                and back_hours > route.max_duration_return_hours):
            return False
        return True

    def _meets_hard_constraints(self, option: TripOption, route: RoutePreference) -> bool:
        # An unknown price can't be compared to a budget. Dropping the option
        # would hide a real connection over a number we don't have; keeping it
        # is honest, and it is clearly labelled as price-less further down.
        if route.budget is not None and not option.has_unknown_price and option.total_price > route.budget:
            return False
        if option.mode != Mode.HOTEL and not self._within_duration_limits(option, route):
            return False
        if route.low_cost == "exclude" and any(o.is_low_cost for o in option.offers):
            return False
        if route.low_cost == "only":
            # Only transport legs can be low-cost; a hotel leg in a combo
            # must not disqualify the option.
            transport = [o for o in option.offers if o.mode in TRANSPORT_MODES]
            if not transport or not all(o.is_low_cost for o in transport):
                return False
        for offer in option.offers:
            if offer.mode == Mode.HOTEL and not _meets_hotel_constraints(offer, route.hotel):
                return False
            if offer.mode in (Mode.FLIGHT, Mode.TRAIN, Mode.BUS) and not _meets_transport_constraints(offer, route.transport):
                return False
        return True

    def _score(self, option: TripOption, priority: Priority, all_candidates: list[TripOption],
                route: RoutePreference | None = None) -> float:
        if priority == Priority.CHEAPEST:
            return option.total_price
        if priority == Priority.MOST_EXPENSIVE:
            return -option.total_price  # engine sorts ascending, so negate
        if priority == Priority.FASTEST:
            return option.total_duration_hours
        if priority == Priority.EXACT_DATE:
            # Days away from the requested window (0 = exactly on a wanted
            # date). Price breaks ties so the ordering stays deterministic
            # instead of depending on provider order.
            return _date_deviation_days(option, route) * 100_000 + option.total_price
        # Normalize against priced candidates only - a placeholder 0.0 would
        # otherwise become the price minimum and squash every real one.
        priced = [c for c in all_candidates if not c.has_unknown_price] or all_candidates
        prices = [c.total_price for c in priced]
        durations = [c.total_duration_hours for c in priced]
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

        if option.has_unknown_price:
            # Every remaining annotation is about money: savings hints,
            # currency equivalents, price-drop/error-fare detection, and
            # feeding the price history. None of them may run on a
            # placeholder price - so say what is known and stop here.
            line = transport_offer.line_label or transport_offer.booking_site
            option.recommendations.append(
                f"🕓 Echte Verbindung laut Fahrplan ({line}) – "
                "Preis liefert diese Quelle nicht, bitte beim Anbieter prüfen."
            )
            return

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
        elif option.is_below_median:
            option.recommendations.insert(0, "🏷️ Deutlich günstiger als der Durchschnitt dieser Suche.")
        self.price_history.record(route_key, transport_offer.mode.value, option.total_price, option.currency, self.as_of)

    def _add_later_departure_hint(self, option: TripOption, offer: Offer, pool: list[Offer],
                                   route: RoutePreference) -> None:
        if offer.mode not in (Mode.FLIGHT, Mode.TRAIN, Mode.BUS):
            return
        # Only compare against offers that also satisfy the route's own
        # transport constraints (esp. the depart-time window) - otherwise
        # this could suggest a time the user already said doesn't work for
        # them, which would contradict their own stated flexibility.
        eligible_pool = [o for o in pool if o.price_known and _meets_transport_constraints(o, route.transport)]
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
        if savings / option.total_price < BAGGAGE_SAVINGS_THRESHOLD:
            return
        # Either weight can be "egal" (None) - then just leave that detail out
        # of the sentence rather than printing "None kg".
        carry_on = f" (bis {route.baggage.carry_on_max_kg}kg)" if route.baggage.carry_on_max_kg is not None else ""
        checked = f" ({route.baggage.checked_bag_kg}kg)" if route.baggage.checked_bag_kg is not None else ""
        option.recommendations.append(
            f"🎒 Nur Handgepäck{carry_on} statt {bags}x Koffer{checked} spart {savings} {offer.currency}."
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


def _flag_below_median(candidates: list[TripOption]) -> None:
    """Mark options notably cheaper than the median of this same search.

    Unlike is_price_drop/is_error_fare this needs no accumulated history, so
    it's the only "is this actually a deal?" signal available on a first
    run - and the only one the in-browser search can ever compute. Compared
    per mode, since a bus and a flight are not the same market.
    """
    by_mode: dict[Mode, list[TripOption]] = {}
    for c in candidates:
        # Price-less options neither have a price to compare nor may they drag
        # the median towards zero for the ones that do.
        if c.has_unknown_price:
            continue
        by_mode.setdefault(c.mode, []).append(c)
    for group in by_mode.values():
        if len(group) < MIN_CANDIDATES_FOR_MEDIAN_DEAL:
            continue  # too few to say what "normal" even is
        prices = sorted(c.total_price for c in group)
        mid = len(prices) // 2
        median = prices[mid] if len(prices) % 2 else (prices[mid - 1] + prices[mid]) / 2
        for c in group:
            c.is_below_median = c.total_price <= median * BELOW_MEDIAN_DEAL_RATIO


def _date_deviation_days(option: TripOption, route: RoutePreference | None) -> int:
    """How many days the option's departure sits outside the *exactly*
    requested window (depart_date_from..depart_date_until), ignoring the
    flex_days_before/after padding - that padding widens what gets searched,
    but with EXACT_DATE the user wants the un-padded dates ranked first."""
    if route is None:
        return 0
    try:
        departure = date.fromisoformat(option.offers[0].depart_time[:10])
    except (ValueError, IndexError):
        return 0
    if departure < route.depart_date_from:
        return (route.depart_date_from - departure).days
    if departure > route.depart_date_until:
        return (departure - route.depart_date_until).days
    return 0


def _normalize(value: float, all_values: list[float]) -> float:
    lo, hi = min(all_values), max(all_values)
    if hi == lo:
        return 0.0
    return (value - lo) / (hi - lo)
