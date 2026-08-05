from datetime import date

from traveldeals.models import (MEAL_PLAN_TIERS, PROPERTY_TYPES, Mode,
                                 RoutePreference)
from traveldeals.providers.mock import (MockBusProvider, MockFlightProvider,
                                         MockHotelProvider, MockTrainProvider)


def make_route(**overrides) -> RoutePreference:
    defaults = dict(id="r1", origin="BER", destination="BCN",
                     depart_date_from=date(2026, 9, 10), depart_date_until=date(2026, 9, 10))
    defaults.update(overrides)
    return RoutePreference(**defaults)


def test_one_way_route_has_no_return_depart_time():
    route = make_route(round_trip=False)
    offers = MockFlightProvider(as_of=date(2026, 8, 1)).search(route)
    assert offers
    assert all(o.return_depart_time is None for o in offers)


def test_round_trip_flight_sets_return_depart_time_and_combined_price():
    one_way = make_route(round_trip=False)
    round_trip = make_route(round_trip=True, return_date=date(2026, 9, 17))
    as_of = date(2026, 8, 1)
    one_way_offers = MockFlightProvider(as_of=as_of).search(one_way)
    round_trip_offers = MockFlightProvider(as_of=as_of).search(round_trip)
    assert all(o.return_depart_time is not None for o in round_trip_offers)
    assert all(o.return_depart_time.startswith("2026-09-17") for o in round_trip_offers)
    # combined round-trip price must be strictly more than the one-way price
    # for the same (seeded, deterministic) offer -> a return leg was actually added
    assert round_trip_offers[0].price > one_way_offers[0].price


def test_round_trip_train_sets_return_depart_time():
    route = make_route(round_trip=True, return_date=date(2026, 9, 17))
    offers = MockTrainProvider(as_of=date(2026, 8, 1)).search(route)
    assert offers
    assert all(o.return_depart_time is not None for o in offers)
    assert all(o.return_depart_time.startswith("2026-09-17") for o in offers)


def test_round_trip_bus_sets_return_depart_time():
    route = make_route(round_trip=True, return_date=date(2026, 9, 17))
    offers = MockBusProvider(as_of=date(2026, 8, 1)).search(route)
    assert offers
    assert all(o.return_depart_time is not None for o in offers)
    assert all(o.return_depart_time.startswith("2026-09-17") for o in offers)


def test_hotel_offers_have_valid_property_type_and_meal_plan():
    route = make_route(min_nights=2)
    offers = MockHotelProvider(as_of=date(2026, 8, 1)).search(route)
    assert offers
    assert all(o.property_type in PROPERTY_TYPES for o in offers)
    assert all(o.meal_plan in MEAL_PLAN_TIERS for o in offers)


def test_hotel_offers_populate_new_amenity_flags():
    # wide flex -> 5 candidate check-in days x 3 offers = 15 offers, enough
    # that a ~50/50-odds amenity flag reliably shows up as both true and
    # false rather than flaking on a single unlucky seed.
    route = make_route(min_nights=2, flex_days_after=6)
    offers = MockHotelProvider(as_of=date(2026, 8, 1)).search(route)
    assert len(offers) >= 12
    assert any(o.elevator for o in offers)
    assert any(not o.elevator for o in offers)
