from datetime import date

import requests

from traveldeals.models import RoutePreference
from traveldeals.providers.amadeus import AmadeusFlightProvider, _parse_duration_hours


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
    """Stands in for requests.Session so tests never touch the network.
    `get_responses` lets a test script a sequence of responses (e.g. a 401
    followed by a 200) to exercise the token-refresh path."""

    def __init__(self, token_response=None, get_responses=None):
        self.token_response = token_response or {"access_token": "fake-token"}
        self._get_responses = list(get_responses) if get_responses is not None else [FakeResponse({"data": []})]
        self.calls = []

    def post(self, url, data=None, timeout=None):
        self.calls.append(("post", url, data))
        return FakeResponse(self.token_response)

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append(("get", url, params))
        return self._get_responses.pop(0) if len(self._get_responses) > 1 else self._get_responses[0]


def make_route(**overrides) -> RoutePreference:
    defaults = dict(id="r1", origin="BER", destination="BCN",
                     depart_date_from=date(2026, 9, 10), depart_date_until=date(2026, 9, 10))
    defaults.update(overrides)
    return RoutePreference(**defaults)


AMADEUS_OFFER = {
    "price": {"total": "199.99", "currency": "EUR"},
    "itineraries": [{
        "duration": "PT2H30M",
        "segments": [
            {"departure": {"at": "2026-09-10T09:00:00"}, "arrival": {"at": "2026-09-10T10:15:00"}, "carrierCode": "LH"},
            {"departure": {"at": "2026-09-10T11:00:00"}, "arrival": {"at": "2026-09-10T11:30:00"}, "carrierCode": "LH"},
        ],
    }],
    "validatingAirlineCodes": ["LH"],
    "travelerPricings": [{"fareDetailsBySegment": [{"includedCheckedBags": {"quantity": 0}}]}],
}


def test_parse_duration_hours():
    assert _parse_duration_hours("PT2H30M") == 2.5
    assert _parse_duration_hours("PT45M") == 0.75
    assert _parse_duration_hours("PT5H") == 5.0


def test_not_configured_returns_empty_without_any_request():
    provider = AmadeusFlightProvider(api_key=None, api_secret=None, session=FakeSession())
    assert provider.search(make_route()) == []


def test_maps_amadeus_offer_to_offer_model():
    session = FakeSession(get_responses=[FakeResponse({"data": [AMADEUS_OFFER]})])
    provider = AmadeusFlightProvider(api_key="k", api_secret="s", session=session)
    offers = provider.search(make_route())
    assert len(offers) == 1
    offer = offers[0]
    assert offer.price == 199.99
    assert offer.currency == "EUR"
    assert offer.depart_time == "2026-09-10T09:00:00"
    assert offer.arrive_time == "2026-09-10T11:30:00"
    assert offer.duration_hours == 2.5
    assert offer.stops == 1
    assert offer.checked_bag_fee == 35.0  # no bags included -> heuristic fee
    assert offer.booking_site == "Amadeus (LH)"


def test_included_baggage_means_no_bag_fee():
    offer_with_bags = {**AMADEUS_OFFER, "travelerPricings": [
        {"fareDetailsBySegment": [{"includedCheckedBags": {"quantity": 1}}]}
    ]}
    session = FakeSession(get_responses=[FakeResponse({"data": [offer_with_bags]})])
    provider = AmadeusFlightProvider(api_key="k", api_secret="s", session=session)
    offers = provider.search(make_route())
    assert offers[0].checked_bag_fee == 0.0


def test_refreshes_token_on_401_and_retries():
    session = FakeSession(get_responses=[
        FakeResponse({}, status_code=401),
        FakeResponse({"data": [AMADEUS_OFFER]}),
    ])
    provider = AmadeusFlightProvider(api_key="k", api_secret="s", session=session)
    offers = provider.search(make_route())
    assert len(offers) == 1
    post_calls = [c for c in session.calls if c[0] == "post"]
    assert len(post_calls) == 2  # initial token + refresh after 401


def test_request_exception_on_one_day_does_not_crash_whole_search():
    class FlakySession(FakeSession):
        def get(self, url, headers=None, params=None, timeout=None):
            self.calls.append(("get", url, params))
            if params["departureDate"] == "2026-09-10":
                raise requests.ConnectionError("network down")
            return FakeResponse({"data": [AMADEUS_OFFER]})

    session = FlakySession()
    provider = AmadeusFlightProvider(api_key="k", api_secret="s", session=session)
    route = make_route(depart_date_from=date(2026, 9, 10), depart_date_until=date(2026, 9, 11))
    offers = provider.search(route)
    assert len(offers) == 1  # the 09-11 day still came through
