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


def test_included_baggage_travels_with_the_offer():
    """Freigepäck gehört zum Angebot, nicht zur Suchanfrage: was im Preis
    drin ist, entscheidet der Tarif - nicht der Wunsch des Reisenden."""
    from traveldeals.providers.mock import MockFlightProvider

    offers = MockFlightProvider().search(make_route(modes=[Mode.FLIGHT]))
    assert offers
    for offer in offers:
        if offer.booking_site == "Beispiel-Airline A" and offer.price < 50:
            continue  # der eingebaute Fehlerpreis, ohne Gepäck-Angabe
        assert offer.included_carry_on_kg == 8.0
        # Billigflieger: Handgepäck ja, Koffer nein.
        assert offer.included_checked_bags == (0 if offer.is_low_cost else 1)
        assert offer.included_checked_bag_kg == (None if offer.is_low_cost else 23.0)
        # Nachvollziehbar, woher die Zahl kommt.
        assert offer.baggage_source


def test_baggage_is_unknown_by_default_not_zero():
    """None heißt "keine Angabe" und ist etwas anderes als "nicht
    enthalten" - eine Quelle, die schweigt, darf nicht als "kein Gepäck"
    dargestellt werden."""
    from traveldeals.models import Mode as M, Offer

    offer = Offer(mode=M.TRAIN, provider="x", booking_site="y", price=1.0,
                  currency="EUR", depart_time="2026-09-15T09:00:00",
                  arrive_time="2026-09-15T11:00:00", duration_hours=2.0)
    assert offer.included_carry_on_kg is None
    assert offer.included_checked_bag_kg is None
    assert offer.included_checked_bags == 0
    assert offer.baggage_source == ""
