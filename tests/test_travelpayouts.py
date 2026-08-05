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


NESTED_SAMPLE_PAYLOAD = {
    # The real API observed in production nests one level deeper than the
    # documented example (SAMPLE_PAYLOAD above) - keyed by an arbitrary index
    # ("0") instead of the offer fields sitting directly under the
    # destination code. This must not silently produce zero offers.
    "success": True,
    "currency": "eur",
    "data": {
        "BCN": {
            "0": {
                "airline": "VY", "flight_number": 1883, "price": 122,
                "departure_at": "2026-09-04T13:50:00+02:00",
                "return_at": "2026-09-07T22:15:00+02:00",
                "expires_at": "2026-08-05T21:33:54Z",
                "duration": 825, "duration_to": 165, "duration_back": 225,
            }
        }
    },
}


def test_maps_real_nested_response_shape():
    session = FakeSession(get_responses=[FakeResponse(NESTED_SAMPLE_PAYLOAD)])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offers = provider.search(make_route())
    assert len(offers) == 1
    offer = offers[0]
    assert offer.price == 122
    assert offer.depart_time == "2026-09-04T13:50:00"  # UTC offset stripped, not just "Z"
    assert offer.booking_site == "Aviasales (VY1883)"


def test_booking_url_is_a_real_working_deep_link_with_return_date():
    session = FakeSession(get_responses=[FakeResponse(NESTED_SAMPLE_PAYLOAD)])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offer = provider.search(make_route())[0]
    assert offer.url.startswith("https://search.aviasales.com/flights/?")
    assert "origin_iata=BER" in offer.url
    assert "destination_iata=BCN" in offer.url
    assert "depart_date=2026-09-04" in offer.url
    assert "return_date=2026-09-07" in offer.url  # from return_at in the sample payload
    assert "one_way=false" in offer.url


def test_booking_url_is_one_way_without_return_at():
    payload = {**SAMPLE_PAYLOAD, "data": {"BCN": {**SAMPLE_PAYLOAD["data"]["BCN"]}}}
    del payload["data"]["BCN"]["expires_at"]
    session = FakeSession(get_responses=[FakeResponse(payload)])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offer = provider.search(make_route())[0]
    assert "one_way=true" in offer.url
    assert "return_date" not in offer.url


def test_duration_to_is_used_directly_when_present():
    session = FakeSession(get_responses=[FakeResponse(NESTED_SAMPLE_PAYLOAD)])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offer = provider.search(make_route())[0]
    assert offer.duration_hours == 2.75  # 165 minutes
    assert offer.arrive_time == "2026-09-04T16:35:00"


def test_duration_to_used_even_when_offer_has_a_connection():
    # duration_to is real data (unlike our own distance guess), so it should
    # be trusted even for offers with a layover, where the geo-estimate
    # fallback deliberately refuses to guess.
    payload = {**NESTED_SAMPLE_PAYLOAD, "data": {"BCN": {"0": {
        **NESTED_SAMPLE_PAYLOAD["data"]["BCN"]["0"], "transfers": 1,
    }}}}
    session = FakeSession(get_responses=[FakeResponse(payload)])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offer = provider.search(make_route())[0]
    assert offer.stops == 1
    assert offer.duration_hours == 2.75


def test_round_trip_route_sends_return_date_param():
    session = FakeSession(get_responses=[FakeResponse(NESTED_SAMPLE_PAYLOAD)])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    route = make_route(round_trip=True, return_date=date(2026, 9, 17))
    provider.search(route)
    _, _, _, params = session.calls[0]
    assert params["return_date"] == "2026-09-17"


def test_one_way_route_omits_return_date_param():
    session = FakeSession(get_responses=[FakeResponse(NESTED_SAMPLE_PAYLOAD)])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    provider.search(make_route(round_trip=False))
    _, _, _, params = session.calls[0]
    assert "return_date" not in params


def test_return_depart_time_populated_from_return_at():
    session = FakeSession(get_responses=[FakeResponse(NESTED_SAMPLE_PAYLOAD)])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offer = provider.search(make_route(round_trip=True, return_date=date(2026, 9, 17)))[0]
    assert offer.return_depart_time == "2026-09-07T22:15:00"  # tz offset stripped, like depart_time


def test_return_depart_time_is_none_without_return_at():
    session = FakeSession(get_responses=[FakeResponse(SAMPLE_PAYLOAD)])  # no return_at field
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offer = provider.search(make_route())[0]
    assert offer.return_depart_time is None


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
