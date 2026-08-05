from datetime import date

import requests

from traveldeals.models import RoutePreference
from traveldeals.providers.travelpayouts import TravelpayoutsFlightProvider


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
    def __init__(self, get_responses=None):
        self._get_responses = list(get_responses) if get_responses is not None else [FakeResponse({"success": True, "data": {}})]
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append(("get", url, headers, params))
        return self._get_responses.pop(0) if len(self._get_responses) > 1 else self._get_responses[0]


def make_route(**overrides) -> RoutePreference:
    defaults = dict(id="r1", origin="BER", destination="BCN",
                     depart_date_from=date(2026, 9, 10), depart_date_until=date(2026, 9, 10))
    defaults.update(overrides)
    return RoutePreference(**defaults)


SAMPLE_PAYLOAD = {
    "success": True,
    "currency": "eur",
    "data": {
        "BCN": {
            "origin": "BER", "destination": "BCN", "price": 89.5, "transfers": 0,
            "airline": "FR", "flight_number": 1234,
            "departure_at": "2026-09-10T09:00:00Z", "expires_at": "2026-09-01T00:00:00Z",
        }
    },
}


def test_not_configured_returns_empty_without_any_request():
    provider = TravelpayoutsFlightProvider(token=None, session=FakeSession())
    assert provider.search(make_route()) == []


def test_maps_response_to_offer_model():
    session = FakeSession(get_responses=[FakeResponse(SAMPLE_PAYLOAD)])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offers = provider.search(make_route())
    assert len(offers) == 1
    offer = offers[0]
    assert offer.price == 89.5
    assert offer.currency == "EUR"
    assert offer.depart_time == "2026-09-10T09:00:00"  # trailing Z stripped
    assert offer.stops == 0
    assert offer.booking_site == "Aviasales (FR1234)"
    # auth header actually sent
    _, _, headers, params = session.calls[0]
    assert headers["X-Access-Token"] == "tok"
    assert params["origin"] == "BER"
    assert params["destination"] == "BCN"


def test_direct_offer_gets_distance_based_duration_estimate():
    session = FakeSession(get_responses=[FakeResponse(SAMPLE_PAYLOAD)])  # transfers: 0, BER->BCN
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offer = provider.search(make_route())[0]
    assert 1.0 < offer.duration_hours < 4.0  # BER-BCN is ~1900km, sanity range
    assert offer.arrive_time != offer.depart_time


def test_connecting_offer_keeps_duration_unknown():
    payload = {**SAMPLE_PAYLOAD, "data": {"BCN": {**SAMPLE_PAYLOAD["data"]["BCN"], "transfers": 1}}}
    session = FakeSession(get_responses=[FakeResponse(payload)])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offer = provider.search(make_route())[0]
    assert offer.stops == 1
    assert offer.duration_hours == 0.0  # layover length is unknowable from distance alone
    assert offer.arrive_time == offer.depart_time


def test_unknown_airport_falls_back_to_unknown_duration():
    payload = {**SAMPLE_PAYLOAD, "data": {"XYZ": {**SAMPLE_PAYLOAD["data"]["BCN"], "transfers": 0}}}
    session = FakeSession(get_responses=[FakeResponse(payload)])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    route = make_route(origin="ZZZ", destination="YYY")  # not in the airport table
    offer = provider.search(route)[0]
    assert offer.duration_hours == 0.0


def test_unsuccessful_response_returns_empty_list():
    session = FakeSession(get_responses=[FakeResponse({"success": False, "data": {}})])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    assert provider.search(make_route()) == []


def test_request_exception_on_one_day_does_not_crash_whole_search():
    class FlakySession(FakeSession):
        def get(self, url, headers=None, params=None, timeout=None):
            self.calls.append(("get", url, headers, params))
            if params["depart_date"] == "2026-09-10":
                raise requests.ConnectionError("network down")
            return FakeResponse(SAMPLE_PAYLOAD)

    session = FlakySession()
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    route = make_route(depart_date_from=date(2026, 9, 10), depart_date_until=date(2026, 9, 11))
    offers = provider.search(route)
    assert len(offers) == 1  # the 09-11 day still came through
