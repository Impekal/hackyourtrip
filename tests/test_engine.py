from datetime import date

from traveldeals.engine import DealEngine
from traveldeals.models import (BaggagePref, Mode, Offer, Priority,
                                 RoutePreference)
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
    route = make_route(baggage=BaggagePref(checked_bags=1))
    result = engine.search(route)
    assert any("Handgepäck" in r for r in result[0].recommendations)


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
