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


def test_low_cost_excluded_when_not_allowed(tmp_path):
    offers = [
        Offer(mode=Mode.FLIGHT, provider="p", booking_site="A", price=50, currency="EUR",
              depart_time="2026-09-10T09:00:00", arrive_time="2026-09-10T11:00:00", duration_hours=2,
              is_low_cost=True),
    ]
    engine = make_engine({Mode.FLIGHT: FakeProvider(Mode.FLIGHT, offers)}, tmp_path)
    route = make_route(low_cost_airlines_ok=False)
    result = engine.search(route)
    assert result == []


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
