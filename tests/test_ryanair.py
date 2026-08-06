"""Ryanair fare finder + merging several flight sources.

The fixtures below are trimmed from what the live service actually returned
for BER->BCN (captured through a throwaway GitHub-Actions workflow, since
this dev sandbox has no internet), so the parsing runs against real field
names, real nesting, and real timestamp formats.
"""
from datetime import date

import requests

from traveldeals.models import Mode, Offer, RoutePreference
from traveldeals.providers.base import CompositeProvider, Provider
from traveldeals.providers.ryanair import RyanairFlightProvider

ONE_WAY_FARE = {
    "outbound": {
        "departureAirport": {"iataCode": "BER", "name": "Berlin Brandenburg"},
        "arrivalAirport": {"iataCode": "BCN", "name": "Barcelona El Prat"},
        "departureDate": "2026-09-25T22:20:00",
        "arrivalDate": "2026-09-26T00:55:00",
        "price": {"value": 53.36, "currencyCode": "EUR", "currencySymbol": "€"},
        "flightKey": "FR~ 132~ ~~BER~09/25/2026 22:20~BCN~09/26/2026 00:55~~",
        "flightNumber": "FR132",
    },
    "summary": {"price": {"value": 53.36, "currencyCode": "EUR"}},
}
ROUND_TRIP_FARE = {
    "outbound": {
        "departureDate": "2026-09-18T22:20:00",
        "arrivalDate": "2026-09-19T00:55:00",
        "price": {"value": 59.76, "currencyCode": "EUR"},
        "flightNumber": "FR132",
    },
    "inbound": {
        "departureDate": "2026-09-21T06:30:00",
        "arrivalDate": "2026-09-21T09:05:00",
        "price": {"value": 41.24, "currencyCode": "EUR"},
        "flightNumber": "FR133",
    },
    "summary": {"price": {"value": 101.0, "currencyCode": "EUR"}},
}


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


class FakeSession:
    def __init__(self, fares=None, status_code=200):
        self.fares = [ONE_WAY_FARE] if fares is None else fares
        self.status_code = status_code
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, headers))
        return FakeResponse({"fares": self.fares}, self.status_code)


def make_route(**overrides) -> RoutePreference:
    defaults = dict(
        id="ber-bcn", origin="BER", destination="BCN",
        depart_date_from=date(2026, 9, 25), depart_date_until=date(2026, 9, 25),
        modes=[Mode.FLIGHT],
    )
    defaults.update(overrides)
    return RoutePreference(**defaults)


# -- parsing -----------------------------------------------------------------

def test_one_way_fare_becomes_a_real_priced_offer():
    offer = RyanairFlightProvider(session=FakeSession()).search(make_route())[0]

    assert offer.provider == "ryanair"
    assert offer.price == 53.36
    assert offer.currency == "EUR"
    assert offer.price_known is True  # unlike Transitous, this is a real fare
    assert offer.depart_time == "2026-09-25T22:20:00"
    assert offer.arrive_time == "2026-09-26T00:55:00"
    assert offer.duration_hours == 2.58
    assert offer.booking_site == "Ryanair (FR132)"
    assert offer.line_label == "FR132"
    assert offer.stops == 0
    assert offer.is_low_cost is True


def test_booking_url_points_at_the_airline_with_the_searched_date():
    offer = RyanairFlightProvider(session=FakeSession()).search(make_route())[0]

    assert offer.url.startswith("https://www.ryanair.com/de/de/trip/flights/select?")
    assert "originIata=BER" in offer.url
    assert "destinationIata=BCN" in offer.url
    assert "dateOut=2026-09-25" in offer.url
    assert "isReturn=false" in offer.url


def test_round_trip_uses_the_combined_total_not_one_leg():
    session = FakeSession(fares=[ROUND_TRIP_FARE])
    route = make_route(round_trip=True, return_date=date(2026, 9, 21),
                       depart_date_from=date(2026, 9, 18), depart_date_until=date(2026, 9, 18))
    offer = RyanairFlightProvider(session=session).search(route)[0]

    # 59.76 (outbound) alone would understate what the trip costs.
    assert offer.price == 101.0
    assert offer.return_depart_time == "2026-09-21T06:30:00"
    assert "isReturn=true" in offer.url and "dateIn=2026-09-21" in offer.url


def test_round_trip_asks_the_round_trip_endpoint_with_an_inbound_window():
    session = FakeSession(fares=[ROUND_TRIP_FARE])
    route = make_route(round_trip=True, return_date=date(2026, 9, 21))
    RyanairFlightProvider(session=session).search(route)

    url, params, _ = session.calls[0]
    assert url.endswith("/roundTripFares")
    assert params["inboundDepartureDateFrom"] == "2026-09-21"


def test_flex_window_becomes_one_request_for_the_whole_range():
    session = FakeSession()
    route = make_route(depart_date_from=date(2026, 9, 20), depart_date_until=date(2026, 9, 25),
                       flex_days_before=2, flex_days_after=3)
    RyanairFlightProvider(session=session).search(route)

    # The fare finder takes a date range, so unlike Travelpayouts this needs
    # exactly one call no matter how wide the window is.
    assert len(session.calls) == 1
    _, params, _ = session.calls[0]
    assert params["outboundDepartureDateFrom"] == "2026-09-18"
    assert params["outboundDepartureDateTo"] == "2026-09-28"


def test_browser_user_agent_is_sent():
    # A plain script UA gets 403 on some Ryanair hosts.
    session = FakeSession()
    RyanairFlightProvider(session=session).search(make_route())
    assert "Mozilla" in session.calls[0][2]["User-Agent"]


def test_fare_without_a_price_is_skipped_rather_than_priced_at_zero():
    broken = {"outbound": {"departureDate": "2026-09-25T22:20:00",
                            "arrivalDate": "2026-09-26T00:55:00", "flightNumber": "FR1"}}
    assert RyanairFlightProvider(session=FakeSession(fares=[broken])).search(make_route()) == []


def test_http_error_returns_nothing_instead_of_raising():
    assert RyanairFlightProvider(session=FakeSession(status_code=500)).search(make_route()) == []


def test_network_failure_is_survived():
    class BrokenSession(FakeSession):
        def get(self, *a, **kw):
            raise requests.ConnectionError("boom")

    assert RyanairFlightProvider(session=BrokenSession()).search(make_route()) == []


# -- merging several sources -------------------------------------------------

class StubProvider(Provider):
    mode = Mode.FLIGHT

    def __init__(self, offers, boom=False):
        self._offers = offers
        self._boom = boom

    def search(self, route):
        if self._boom:
            raise RuntimeError("provider exploded")
        return list(self._offers)


def offer(price, site="Anbieter", hour=9) -> Offer:
    return Offer(mode=Mode.FLIGHT, provider="stub", booking_site=site, price=price,
                 currency="EUR", depart_time=f"2026-09-25T{hour:02d}:00:00",
                 arrive_time=f"2026-09-25T{hour + 2:02d}:00:00", duration_hours=2.0)


def test_composite_merges_both_pools():
    composite = CompositeProvider(Mode.FLIGHT, [
        StubProvider([offer(53.36, "Ryanair (FR132)")]),
        StubProvider([offer(120.0, "Kiwi.com (LH1998)", hour=14)]),
    ])
    prices = [o.price for o in composite.search(make_route())]
    assert prices == [53.36, 120.0]


def test_composite_drops_the_same_flight_seen_twice():
    same = offer(53.36, "Ryanair (FR132)")
    composite = CompositeProvider(Mode.FLIGHT, [StubProvider([same]), StubProvider([same])])
    assert len(composite.search(make_route())) == 1


def test_one_broken_source_does_not_sink_the_others():
    composite = CompositeProvider(Mode.FLIGHT, [
        StubProvider([], boom=True),
        StubProvider([offer(53.36)]),
    ])
    # A partial result beats an empty one.
    assert [o.price for o in composite.search(make_route())] == [53.36]
