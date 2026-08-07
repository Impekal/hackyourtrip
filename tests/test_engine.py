from datetime import date

from traveldeals.engine import DealEngine
from traveldeals.models import (BaggagePref, HotelPref, Mode, Offer,
                                 Priority, RoutePreference, TransportPref)
from traveldeals.pricehistory import PriceHistory
from traveldeals.providers.base import Provider


class FakeProvider(Provider):
    def __init__(self, mode: Mode, offers: list[Offer]):
        self.mode = mode
        self._offers = offers

    def search(self, route: RoutePreference) -> list[Offer]:
        return self._offers


def make_route(**overrides) -> RoutePreference:
    defaults = dict(
        id="r1", origin="BER", destination="BCN",
        depart_date_from=date(2026, 9, 10), depart_date_until=date(2026, 9, 10),
        modes=[Mode.FLIGHT], priority=Priority.CHEAPEST,
    )
    defaults.update(overrides)
    return RoutePreference(**defaults)


def make_engine(providers: dict[Mode, Provider], tmp_path) -> DealEngine:
    hist = PriceHistory(tmp_path / "history.json")
    return DealEngine(providers, hist, as_of=date(2026, 9, 1), use_live_currency=False)


def test_cheapest_priority_picks_lowest_price(tmp_path):
    offers = [
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="A", price=150, currency="EUR",
              depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T11:00:00", duration_hours=2),
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="B", price=90, currency="EUR",
              depart_time="2026-09-10T14:00:00", arrive_time="2026-09-10T17:00:00", duration_hours=3),
    ]
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, tmp_path)
    route = make_route(priority=Priority.CHEAPEST)
    result = engine.search(route)
    assert result[0].total_price == 90


def test_fastest_priority_picks_lowest_duration_and_flags_later_cheaper_option(tmp_path):
    offers = [
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="A", price=150, currency="EUR",
              depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T11:00:00", duration_hours=2),
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="B", price=90, currency="EUR",
              depart_time="2026-09-10T14:00:00", arrive_time="2026-09-10T17:00:00", duration_hours=3),
    ]
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, tmp_path)
    route = make_route(priority=Priority.FASTEST)
    result = engine.search(route)
    top = result[0]
    assert top.total_duration_hours == 2
    assert top.total_price == 150
    assert any("später" in r for r in top.recommendations)


def test_budget_filters_out_offers_over_limit(tmp_path):
    offers = [
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="A", price=500, currency="EUR",
              depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T11:00:00", duration_hours=2),
    ]
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, tmp_path)
    route = make_route(budget=100)
    result = engine.search(route)
    assert result == []


def _lowcost_offers():
    return [
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="billig", price=50, currency="EUR",
              depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T11:00:00", duration_hours=2,
              is_low_cost=True),
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="normal", price=180, currency="EUR",
              depart_time="2026-09-10T12:00:00", arrive_time="2026-09-10T14:00:00", duration_hours=2,
              is_low_cost=False),
    ]


def test_low_cost_exclude_drops_low_cost_offers(tmp_path):
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, _lowcost_offers())}, tmp_path)
    result = engine.search(make_route(low_cost="exclude"))
    assert [o.booking_sites[0] for o in result] == ["normal"]


def test_low_cost_only_keeps_just_low_cost_offers(tmp_path):
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, _lowcost_offers())}, tmp_path)
    result = engine.search(make_route(low_cost="only"))
    assert [o.booking_sites[0] for o in result] == ["billig"]


def test_low_cost_any_keeps_everything(tmp_path):
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, _lowcost_offers())}, tmp_path)
    assert len(engine.search(make_route(low_cost="any"))) == 2


def test_low_cost_only_ignores_the_hotel_leg_of_a_combo(tmp_path):
    # A hotel is never "low cost"; requiring it to be would wipe out every
    # flight+hotel combo, which is not what the filter means.
    flight = Offer(mode=Mode.FLIGHT, provider="p", booking_site="billig", price=50, currency="EUR",
                   depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T11:00:00",
                   duration_hours=2, is_low_cost=True)
    hotel = Offer(mode=Mode.HOTEL, provider="p", booking_site="hotel", price=100, currency="EUR",
                  depart_time="2026-09-10T00:00:00", arrive_time="2026-09-12T00:00:00",
                  duration_hours=48)
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, [flight]),
                          Mode.HOTEL: FakeProvider(Mode.HOTEL, [hotel])}, tmp_path)
    route = make_route(modes=[Mode.FLIGHT_HOTEL], low_cost="only", min_nights=2)
    assert len(engine.search(route)) == 1


def test_most_expensive_priority_reverses_price_order(tmp_path):
    offers = [
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="A", price=150, currency="EUR",
              depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T11:00:00", duration_hours=2),
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="B", price=90, currency="EUR",
              depart_time="2026-09-10T14:00:00", arrive_time="2026-09-10T17:00:00", duration_hours=3),
    ]
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, tmp_path)
    result = engine.search(make_route(priority=Priority.MOST_EXPENSIVE))
    assert [o.total_price for o in result] == [150, 90]


def test_exact_date_priority_ranks_requested_dates_first(tmp_path):
    offers = [
        # cheapest, but 3 days off the requested date - must NOT win here
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="cheap-but-off", price=50, currency="EUR",
              depart_time="2026-09-13T09:00:00", arrive_time="2026-09-13T11:00:00", duration_hours=2),
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="exact", price=200, currency="EUR",
              depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T11:00:00", duration_hours=2),
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="one-day-off", price=80, currency="EUR",
              depart_time="2026-09-11T09:00:00", arrive_time="2026-09-11T11:00:00", duration_hours=2),
    ]
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, tmp_path)
    route = make_route(priority=Priority.EXACT_DATE, flex_days_after=5)
    result = engine.search(route)
    assert [o.booking_sites[0] for o in result] == ["exact", "one-day-off", "cheap-but-off"]


def test_exact_date_priority_falls_back_to_price_within_the_window(tmp_path):
    offers = [
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="pricey", price=300, currency="EUR",
              depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T11:00:00", duration_hours=2),
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="cheap", price=100, currency="EUR",
              depart_time="2026-09-11T09:00:00", arrive_time="2026-09-11T11:00:00", duration_hours=2),
    ]
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, tmp_path)
    # both days are inside the requested window -> zero deviation for both,
    # so price decides rather than provider order
    route = make_route(priority=Priority.EXACT_DATE, depart_date_until=date(2026, 9, 11))
    result = engine.search(route)
    assert result[0].booking_sites[0] == "cheap"


def _flight(price, day="10", site="X"):
    return Offer(mode=Mode.FLIGHT, provider="p", booking_site=site, price=price, currency="EUR",
                 depart_time=f"2026-09-{day}T09:00:00", arrive_time=f"2026-09-{day}T11:00:00",
                 duration_hours=2)


def test_deals_only_keeps_just_the_notably_cheap_offers(tmp_path):
    # median of 100/100/100/100/50 is 100 -> only the 50 clears the
    # below-median threshold
    offers = [_flight(100, site=f"n{i}") for i in range(4)] + [_flight(50, site="deal")]
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, tmp_path)
    result = engine.search(make_route(deals_only=True))
    assert [o.booking_sites[0] for o in result] == ["deal"]
    assert result[0].is_deal


def test_deals_only_off_returns_everything(tmp_path):
    offers = [_flight(100, site=f"n{i}") for i in range(4)] + [_flight(50, site="deal")]
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, tmp_path)
    assert len(engine.search(make_route(deals_only=False))) == 5


def test_deals_only_can_come_up_empty_rather_than_inventing_deals(tmp_path):
    # all the same price -> nothing is below median, so "only deals" is
    # honestly empty instead of silently showing normal fares
    offers = [_flight(100, site=f"n{i}") for i in range(5)]
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, tmp_path)
    assert engine.search(make_route(deals_only=True)) == []


def test_below_median_needs_enough_candidates_to_be_meaningful(tmp_path):
    # with only 2 offers a "median" says nothing, so neither is flagged
    offers = [_flight(100, site="a"), _flight(50, site="b")]
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, tmp_path)
    assert all(not o.is_below_median for o in engine.search(make_route()))


def test_below_median_deal_is_explained_in_recommendations(tmp_path):
    offers = [_flight(100, site=f"n{i}") for i in range(4)] + [_flight(50, site="deal")]
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, tmp_path)
    deal = engine.search(make_route(priority=Priority.CHEAPEST))[0]
    assert any("günstiger als der Durchschnitt" in r for r in deal.recommendations)


def test_baggage_hint_when_checked_bag_fee_significant(tmp_path):
    offers = [
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="A", price=100, currency="EUR",
              depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T11:00:00", duration_hours=2,
              checked_bag_fee=30),
    ]
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, tmp_path)
    route = make_route(baggage=BaggagePref(checked_bags=1, carry_on_max_kg=8))
    result = engine.search(route)
    assert any("Handgepäck" in r and "8kg" in r for r in result[0].recommendations)


def test_baggage_hint_omits_weights_when_set_to_egal(tmp_path):
    offers = [
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="A", price=100, currency="EUR",
              depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T11:00:00", duration_hours=2,
              checked_bag_fee=30),
    ]
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, tmp_path)
    route = make_route(baggage=BaggagePref(checked_bags=1, checked_bag_kg=None, carry_on_max_kg=None))
    hint = next(r for r in engine.search(route)[0].recommendations if "Handgepäck" in r)
    assert "None" not in hint  # "egal" must not leak a literal None into the text
    assert "kg" not in hint


def test_flight_hotel_combo_pairs_same_day_cheapest_hotel(tmp_path):
    flight = Offer(mode=Mode.FLIGHT, provider="p", booking_site="A", price=100, currency="EUR",
                    depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T11:00:00", duration_hours=2)
    hotel_cheap = Offer(mode=Mode.HOTEL, provider="p", booking_site="Booking.com", price=200, currency="EUR",
                         depart_time="2026-09-10T00:00:00", arrive_time="2026-09-14T00:00:00", duration_hours=96)
    hotel_expensive = Offer(mode=Mode.HOTEL, provider="p", booking_site="Trivago", price=400, currency="EUR",
                             depart_time="2026-09-10T00:00:00", arrive_time="2026-09-14T00:00:00", duration_hours=96)
    engine = make_engine({
        Mode.FLIGHT: FakeProvider(Mode.FLIGHT, [flight]),
        Mode.HOTEL: FakeProvider(Mode.HOTEL, [hotel_cheap, hotel_expensive]),
    }, tmp_path)
    route = make_route(modes=[Mode.FLIGHT_HOTEL])
    result = engine.search(route)
    assert len(result) == 1
    assert result[0].total_price == 300  # 100 + 200 (cheapest hotel), not 400


def test_error_fare_flagged_against_history(tmp_path):
    offers = [
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="A", price=20, currency="EUR",
              depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T11:00:00", duration_hours=2),
    ]
    hist = PriceHistory(tmp_path / "history.json")
    route_key = "BER->BCN:flight"
    for i, price in enumerate([100, 110, 105]):
        hist.record(route_key, "flight", price, "EUR", date(2026, 8, 1 + i))
    engine = DealEngine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, hist,
                         as_of=date(2026, 9, 1), use_live_currency=False)
    route = make_route()
    result = engine.search(route)
    assert result[0].is_error_fare is True


def test_flight_or_train_combo_merges_both_pools_and_picks_cheapest(tmp_path):
    flight = Offer(mode=Mode.FLIGHT, provider="p", booking_site="A", price=200, currency="EUR",
                    depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T11:00:00", duration_hours=2)
    train = Offer(mode=Mode.TRAIN, provider="p", booking_site="B", price=60, currency="EUR",
                   depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T15:00:00", duration_hours=6)
    engine = make_engine({
        Mode.FLIGHT: FakeProvider(Mode.FLIGHT, [flight]),
        Mode.TRAIN: FakeProvider(Mode.TRAIN, [train]),
    }, tmp_path)
    route = make_route(modes=[Mode.FLIGHT_OR_TRAIN], priority=Priority.CHEAPEST)
    result = engine.search(route)
    assert result[0].total_price == 60
    assert result[0].offers[0].mode == Mode.TRAIN
    assert result[0].mode == Mode.FLIGHT_OR_TRAIN


def test_hotel_min_stars_filter_excludes_low_rated(tmp_path):
    offers = [
        Offer(mode=Mode.HOTEL, provider="p", booking_site="Booking.com", price=100, currency="EUR",
              depart_time="2026-09-10T00:00:00", arrive_time="2026-09-14T00:00:00", duration_hours=96,
              stars=2, rating=6.0),
        Offer(mode=Mode.HOTEL, provider="p", booking_site="Booking.com", price=150, currency="EUR",
              depart_time="2026-09-10T00:00:00", arrive_time="2026-09-14T00:00:00", duration_hours=96,
              stars=4, rating=8.5),
    ]
    engine = make_engine({Mode.HOTEL: FakeProvider(Mode.HOTEL, offers)}, tmp_path)
    route = make_route(modes=[Mode.HOTEL], hotel=HotelPref(min_stars=3))
    result = engine.search(route)
    assert len(result) == 1
    assert result[0].total_price == 150


def test_hotel_required_amenity_filter(tmp_path):
    offers = [
        Offer(mode=Mode.HOTEL, provider="p", booking_site="Booking.com", price=100, currency="EUR",
              depart_time="2026-09-10T00:00:00", arrive_time="2026-09-14T00:00:00", duration_hours=96,
              free_cancellation=False),
        Offer(mode=Mode.HOTEL, provider="p", booking_site="Booking.com", price=120, currency="EUR",
              depart_time="2026-09-10T00:00:00", arrive_time="2026-09-14T00:00:00", duration_hours=96,
              free_cancellation=True),
    ]
    engine = make_engine({Mode.HOTEL: FakeProvider(Mode.HOTEL, offers)}, tmp_path)
    route = make_route(modes=[Mode.HOTEL], hotel=HotelPref(require_free_cancellation=True))
    result = engine.search(route)
    assert len(result) == 1
    assert result[0].total_price == 120


def test_hotel_min_meal_plan_filter(tmp_path):
    offers = [
        Offer(mode=Mode.HOTEL, provider="p", booking_site="Booking.com", price=100, currency="EUR",
              depart_time="2026-09-10T00:00:00", arrive_time="2026-09-14T00:00:00", duration_hours=96,
              meal_plan="none"),
        Offer(mode=Mode.HOTEL, provider="p", booking_site="Booking.com", price=120, currency="EUR",
              depart_time="2026-09-10T00:00:00", arrive_time="2026-09-14T00:00:00", duration_hours=96,
              meal_plan="breakfast"),
        Offer(mode=Mode.HOTEL, provider="p", booking_site="Booking.com", price=140, currency="EUR",
              depart_time="2026-09-10T00:00:00", arrive_time="2026-09-14T00:00:00", duration_hours=96,
              meal_plan="all_inclusive"),
    ]
    engine = make_engine({Mode.HOTEL: FakeProvider(Mode.HOTEL, offers)}, tmp_path)
    route = make_route(modes=[Mode.HOTEL], hotel=HotelPref(min_meal_plan="breakfast"))
    result = engine.search(route)
    assert {r.total_price for r in result} == {120, 140}


def test_hotel_property_type_filter(tmp_path):
    offers = [
        Offer(mode=Mode.HOTEL, provider="p", booking_site="Booking.com", price=90, currency="EUR",
              depart_time="2026-09-10T00:00:00", arrive_time="2026-09-14T00:00:00", duration_hours=96,
              property_type="hostel"),
        Offer(mode=Mode.HOTEL, provider="p", booking_site="Booking.com", price=200, currency="EUR",
              depart_time="2026-09-10T00:00:00", arrive_time="2026-09-14T00:00:00", duration_hours=96,
              property_type="apartment"),
    ]
    engine = make_engine({Mode.HOTEL: FakeProvider(Mode.HOTEL, offers)}, tmp_path)
    route = make_route(modes=[Mode.HOTEL], hotel=HotelPref(property_types=["apartment", "villa"]))
    result = engine.search(route)
    assert len(result) == 1
    assert result[0].total_price == 200


def test_hotel_new_amenity_flags_filter(tmp_path):
    offers = [
        Offer(mode=Mode.HOTEL, provider="p", booking_site="Booking.com", price=100, currency="EUR",
              depart_time="2026-09-10T00:00:00", arrive_time="2026-09-14T00:00:00", duration_hours=96,
              spa=False, sauna=False),
        Offer(mode=Mode.HOTEL, provider="p", booking_site="Booking.com", price=160, currency="EUR",
              depart_time="2026-09-10T00:00:00", arrive_time="2026-09-14T00:00:00", duration_hours=96,
              spa=True, sauna=True),
    ]
    engine = make_engine({Mode.HOTEL: FakeProvider(Mode.HOTEL, offers)}, tmp_path)
    route = make_route(modes=[Mode.HOTEL], hotel=HotelPref(require_spa=True, require_sauna=True))
    result = engine.search(route)
    assert len(result) == 1
    assert result[0].total_price == 160


def test_transport_direct_only_filter(tmp_path):
    offers = [
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="A", price=100, currency="EUR",
              depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T11:00:00", duration_hours=2, stops=1),
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="B", price=150, currency="EUR",
              depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T11:00:00", duration_hours=2, stops=0),
    ]
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, tmp_path)
    route = make_route(transport=TransportPref(direct_only=True))
    result = engine.search(route)
    assert len(result) == 1
    assert result[0].total_price == 150


def test_best_value_prefers_more_comfortable_hotel_at_similar_price(tmp_path):
    basic = Offer(mode=Mode.HOTEL, provider="p", booking_site="Booking.com", price=100, currency="EUR",
                   depart_time="2026-09-10T00:00:00", arrive_time="2026-09-14T00:00:00", duration_hours=96,
                   stars=2, rating=6.0, wifi=False, distance_km=8.0)
    comfy = Offer(mode=Mode.HOTEL, provider="p", booking_site="Booking.com", price=105, currency="EUR",
                   depart_time="2026-09-10T00:00:00", arrive_time="2026-09-14T00:00:00", duration_hours=96,
                   stars=5, rating=9.5, wifi=True, meal_plan="breakfast", free_cancellation=True,
                   parking=True, air_conditioning=True, pool=True, gym=True, distance_km=0.2)
    # a much pricier decoy so basic/comfy both sit near the low end of the
    # price range - with only 2 candidates, min-max normalization would
    # otherwise stretch their small 5 EUR gap to the full 0..1 range and
    # let price dominate regardless of how small the real difference is.
    decoy = Offer(mode=Mode.HOTEL, provider="p", booking_site="Booking.com", price=400, currency="EUR",
                   depart_time="2026-09-10T00:00:00", arrive_time="2026-09-14T00:00:00", duration_hours=96,
                   stars=3, rating=7.0)
    engine = make_engine({Mode.HOTEL: FakeProvider(Mode.HOTEL, [basic, comfy, decoy])}, tmp_path)
    route = make_route(modes=[Mode.HOTEL], priority=Priority.BEST_VALUE)
    result = engine.search(route)
    assert result[0].total_price == 105


def test_preferred_depart_time_filters_offers_outside_the_window(tmp_path):
    offers = [
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="A", price=100, currency="EUR",
              depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T11:00:00", duration_hours=2),
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="B", price=80, currency="EUR",
              depart_time="2026-09-10T21:00:00", arrive_time="2026-09-10T23:00:00", duration_hours=2),
    ]
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, tmp_path)
    route = make_route(transport=TransportPref(preferred_depart_time="09:00", depart_time_flex_minutes=60))
    result = engine.search(route)
    assert len(result) == 1
    assert result[0].total_price == 100  # the cheaper 21:00 offer is outside the +/-60min window


def test_preferred_depart_time_window_wraps_around_midnight(tmp_path):
    offers = [
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="A", price=100, currency="EUR",
              depart_time="2026-09-10T23:45:00", arrive_time="2026-09-11T01:45:00", duration_hours=2),
    ]
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, tmp_path)
    route = make_route(transport=TransportPref(preferred_depart_time="00:15", depart_time_flex_minutes=60))
    result = engine.search(route)
    assert len(result) == 1  # 23:45 is only 30min from 00:15 across midnight


def test_later_departure_hint_never_suggests_a_time_outside_the_window(tmp_path):
    offers = [
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="A", price=100, currency="EUR",
              depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T11:00:00", duration_hours=2),
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="B", price=80, currency="EUR",
              depart_time="2026-09-10T09:30:00", arrive_time="2026-09-10T11:30:00", duration_hours=2),
        # much cheaper, but well outside the user's +/-60min window - must
        # never be suggested even though it would otherwise be the obvious
        # "leave later, save more" pick.
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="C", price=20, currency="EUR",
              depart_time="2026-09-10T21:00:00", arrive_time="2026-09-10T23:00:00", duration_hours=2),
    ]
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, tmp_path)
    # FASTEST with equal durations keeps the 09:00/100 offer on top (stable
    # sort), so the later-departure hint has something to compare against.
    route = make_route(transport=TransportPref(preferred_depart_time="09:00", depart_time_flex_minutes=60),
                        priority=Priority.FASTEST)
    result = engine.search(route)
    assert result[0].total_price == 100
    assert not any("21:00" in r for r in result[0].recommendations)
    assert any("09:30" in r and "20" in r for r in result[0].recommendations)


def test_round_trip_ticket_duration_counts_both_legs():
    """Ein Rückflugticket trägt beide Richtungen in *einem* Angebot. Zählt nur
    der Hinweg, sortiert es sich vor jede aus zwei Einzelfahrten gebaute
    Reise - als bräuchte der Rückweg keine Zeit."""
    from traveldeals.engine import DealEngine

    out_only = Offer(mode=Mode.FLIGHT, provider="x", booking_site="y", price=100.0,
                     currency="EUR", depart_time="2026-09-15T08:00:00",
                     arrive_time="2026-09-15T10:00:00", duration_hours=2.0)
    round_trip = Offer(mode=Mode.FLIGHT, provider="x", booking_site="y", price=100.0,
                       currency="EUR", depart_time="2026-09-15T08:00:00",
                       arrive_time="2026-09-15T10:00:00", duration_hours=2.0,
                       return_depart_time="2026-09-18T18:00:00", return_duration_hours=3.0)

    assert DealEngine._offer_total_duration(out_only) == 2.0
    assert DealEngine._offer_total_duration(round_trip) == 5.0


def test_unknown_return_duration_is_not_mirrored_from_the_outbound():
    """None heißt "die Quelle sagt es nicht" - nicht "genauso lang wie hin"."""
    from traveldeals.engine import DealEngine

    offer = Offer(mode=Mode.FLIGHT, provider="x", booking_site="y", price=100.0,
                  currency="EUR", depart_time="2026-09-15T08:00:00",
                  arrive_time="2026-09-15T10:00:00", duration_hours=2.0,
                  return_depart_time="2026-09-18T18:00:00", return_duration_hours=None)
    assert offer.return_duration_hours is None
    # Die Gesamtdauer bleibt dann der bekannte Teil, statt zu raten.
    assert DealEngine._offer_total_duration(offer) == 2.0
