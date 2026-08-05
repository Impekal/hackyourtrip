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
    """Answers per endpoint, since the provider queries two of them."""

    def __init__(self, get_responses=None, latest_response=None):
        self._get_responses = list(get_responses) if get_responses is not None else [FakeResponse({"success": True, "data": []})]
        self._latest = latest_response or FakeResponse({"success": True, "data": []})
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append(("get", url, headers, params))
        if "prices/latest" in url:
            return self._latest
        return self._get_responses.pop(0) if len(self._get_responses) > 1 else self._get_responses[0]

    @property
    def search_calls(self):
        return [c for c in self.calls if "prices_for_dates" in c[1]]


def make_route(**overrides) -> RoutePreference:
    # The default window covers 2026-09-18, which is the date _raw() departs
    # on - the provider filters month results down to the wanted days.
    defaults = dict(id="r1", origin="BER", destination="BCN",
                     depart_date_from=date(2026, 9, 18), depart_date_until=date(2026, 9, 18))
    defaults.update(overrides)
    return RoutePreference(**defaults)


# Real shape of aviasales/v3/prices_for_dates, captured from the live API.
def _raw(**overrides) -> dict:
    base = {
        "flight_number": "1887",
        "link": "/search/BER1809BCN1?t=VY123&expected_price=38",
        "origin_airport": "BER", "destination_airport": "BCN",
        "departure_at": "2026-09-18T21:55:00+02:00",
        "airline": "VY", "destination": "BCN", "origin": "BER",
        "price": 38, "gate": "Clickavia",
        "return_transfers": 0, "duration": 165, "duration_to": 165,
        "duration_back": 0, "transfers": 0,
    }
    base.update(overrides)
    return base


# Real shape of v2/prices/latest - different field names, no link.
def _latest_raw(**overrides) -> dict:
    base = {
        "depart_date": "2026-09-18", "origin": "BER", "destination": "BCN",
        "gate": "Kiwi.com", "return_date": "", "found_at": "2026-08-04T10:18:14",
        "trip_class": 0, "value": 236, "number_of_changes": 1,
        "duration": 740, "distance": 1502, "show_to_affiliates": True, "actual": True,
    }
    base.update(overrides)
    return base


def payload(*rows, currency="eur") -> dict:
    return {"success": True, "currency": currency, "data": list(rows)}


def test_not_configured_returns_empty_without_any_request():
    provider = TravelpayoutsFlightProvider(token=None, session=FakeSession())
    assert provider.search(make_route()) == []


def test_maps_response_to_offer_model():
    session = FakeSession(get_responses=[FakeResponse(payload(_raw()))])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offers = provider.search(make_route())
    assert len(offers) == 1
    offer = offers[0]
    assert offer.price == 38
    assert offer.currency == "EUR"
    assert offer.depart_time == "2026-09-18T21:55:00"  # UTC offset stripped
    assert offer.stops == 0
    # the real booking gate is named, not a generic "Aviasales"
    assert offer.booking_site == "Clickavia (VY1887)"
    _, url, headers, params = session.search_calls[0]
    assert headers["X-Access-Token"] == "tok"
    assert params["origin"] == "BER"
    assert params["destination"] == "BCN"
    assert params["sorting"] == "price"


def test_queries_whole_months_not_single_days():
    # Asking for one specific date returns a single offer from this API;
    # asking for the month returns dozens. So the request must be
    # month-shaped, with the day-level filtering done on our side.
    session = FakeSession(get_responses=[FakeResponse(payload(_raw()))])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    provider.search(make_route(depart_date_from=date(2026, 9, 1), depart_date_until=date(2026, 9, 28)))
    months = [c[3]["departure_at"] for c in session.search_calls]
    assert months == ["2026-09"]  # one request for the whole window, not 28


def test_returns_many_offers_per_request_not_just_one():
    # The whole point of moving to prices_for_dates: a single request yields
    # a whole batch of competing offers, not one "cheapest" row.
    rows = [_raw(price=38 + i, gate=f"Gate{i}", flight_number=str(1000 + i)) for i in range(25)]
    session = FakeSession(get_responses=[FakeResponse(payload(*rows))])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    assert len(provider.search(make_route())) == 25


def test_offers_outside_the_requested_window_are_dropped():
    # The month query deliberately over-fetches; the flex window decides.
    rows = [_raw(departure_at="2026-09-18T21:55:00+02:00"),
            _raw(departure_at="2026-09-27T08:00:00+02:00", price=99, gate="Other")]
    session = FakeSession(get_responses=[FakeResponse(payload(*rows))])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offers = provider.search(make_route())  # window is 2026-09-18 only
    assert [o.depart_time[:10] for o in offers] == ["2026-09-18"]


def test_merges_offers_from_the_second_endpoint():
    # v2/prices/latest surfaces partly different itineraries, so its rows
    # should widen the result list rather than be ignored.
    session = FakeSession(get_responses=[FakeResponse(payload(_raw()))],
                           latest_response=FakeResponse(payload(_latest_raw())))
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offers = provider.search(make_route())
    assert {o.booking_site for o in offers} == {"Clickavia (VY1887)", "Kiwi.com"}
    latest = next(o for o in offers if o.booking_site == "Kiwi.com")
    assert latest.price == 236
    assert latest.stops == 1                     # from number_of_changes
    assert latest.duration_hours == round(740 / 60, 2)


def test_second_endpoint_is_skipped_for_round_trips():
    # v2/prices/latest returns nothing for round trips, so don't spend a
    # request on it there.
    session = FakeSession(get_responses=[FakeResponse(payload(_raw()))])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    provider.search(make_route(round_trip=True, return_date=date(2026, 9, 25)))
    assert not any("prices/latest" in c[1] for c in session.calls)


def test_uses_per_itinerary_deep_link_when_present():
    session = FakeSession(get_responses=[FakeResponse(payload(_raw()))])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offer = provider.search(make_route())[0]
    assert offer.url == "https://www.aviasales.com/search/BER1809BCN1?t=VY123&expected_price=38"


def test_falls_back_to_generic_search_url_without_link():
    session = FakeSession(get_responses=[FakeResponse(payload(_raw(link=None)))])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offer = provider.search(make_route())[0]
    assert offer.url.startswith("https://search.aviasales.com/flights/?")
    assert "origin_iata=BER" in offer.url
    assert "one_way=true" in offer.url


def test_duration_to_is_used_directly():
    session = FakeSession(get_responses=[FakeResponse(payload(_raw(duration_to=165)))])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offer = provider.search(make_route())[0]
    assert offer.duration_hours == 2.75  # 165 minutes
    assert offer.arrive_time == "2026-09-19T00:40:00"


def test_duration_to_used_even_when_offer_has_a_connection():
    # duration_to is real data (unlike our own distance guess), so it should
    # be trusted even for offers with a layover, where the geo-estimate
    # fallback deliberately refuses to guess.
    session = FakeSession(get_responses=[FakeResponse(payload(_raw(transfers=1, duration_to=300)))])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offer = provider.search(make_route())[0]
    assert offer.stops == 1
    assert offer.duration_hours == 5.0


def test_connecting_offer_without_duration_keeps_duration_unknown():
    session = FakeSession(get_responses=[FakeResponse(payload(_raw(transfers=1, duration_to=None)))])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offer = provider.search(make_route())[0]
    assert offer.duration_hours == 0.0  # layover length is unknowable from distance alone
    assert offer.arrive_time == offer.depart_time


def test_direct_offer_without_duration_gets_distance_estimate():
    session = FakeSession(get_responses=[FakeResponse(payload(_raw(transfers=0, duration_to=None)))])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    offer = provider.search(make_route())[0]
    assert 1.0 < offer.duration_hours < 4.0  # BER-BCN is ~1500km, sanity range


def test_unknown_airport_falls_back_to_unknown_duration():
    session = FakeSession(get_responses=[FakeResponse(payload(_raw(transfers=0, duration_to=None)))])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    route = make_route(origin="ZZZ", destination="YYY")  # not in the airport table
    assert provider.search(route)[0].duration_hours == 0.0


def test_round_trip_route_sends_return_month_and_sets_return_depart_time():
    row = _raw(return_at="2026-09-25T10:00:00+02:00")
    session = FakeSession(get_responses=[FakeResponse(payload(row))])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    route = make_route(round_trip=True, return_date=date(2026, 9, 25))
    offer = provider.search(route)[0]
    _, _, _, params = session.search_calls[0]
    # a specific return_at date returns zero rows from this API; the return
    # *month* is what works
    assert params["return_at"] == "2026-09"
    assert params["one_way"] == "false"
    assert offer.return_depart_time == "2026-09-25T10:00:00"


def test_one_way_route_omits_return_at():
    session = FakeSession(get_responses=[FakeResponse(payload(_raw()))])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    provider.search(make_route(round_trip=False))
    _, _, _, params = session.search_calls[0]
    assert "return_at" not in params
    assert params["one_way"] == "true"


def test_duplicate_itineraries_across_endpoints_are_deduplicated():
    # Both endpoints index the same market, so an identical itinerary must
    # be listed once rather than twice.
    dup = _latest_raw(gate="Clickavia (VY1887)", value=38, depart_date="2026-09-18", duration=0)
    session = FakeSession(get_responses=[FakeResponse(payload(_raw(departure_at="2026-09-18T00:00:00+02:00")))],
                           latest_response=FakeResponse(payload(dup)))
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    assert len(provider.search(make_route())) == 1


def test_window_spanning_two_months_queries_both():
    session = FakeSession(get_responses=[FakeResponse(payload(_raw()))])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    provider.search(make_route(depart_date_from=date(2026, 9, 28), depart_date_until=date(2026, 10, 3)))
    assert [c[3]["departure_at"] for c in session.search_calls] == ["2026-09", "2026-10"]


def test_unsuccessful_response_returns_empty_list():
    session = FakeSession(get_responses=[FakeResponse({"success": False, "data": []})])
    provider = TravelpayoutsFlightProvider(token="tok", session=session)
    assert provider.search(make_route()) == []


def test_request_exception_on_one_endpoint_does_not_crash_whole_search():
    # If prices_for_dates is down, the results from the other endpoint must
    # still come through rather than the whole search failing.
    class FlakySession(FakeSession):
        def get(self, url, headers=None, params=None, timeout=None):
            self.calls.append(("get", url, headers, params))
            if "prices_for_dates" in url:
                raise requests.ConnectionError("network down")
            return FakeResponse(payload(_latest_raw()))

    provider = TravelpayoutsFlightProvider(token="tok", session=FlakySession())
    offers = provider.search(make_route())
    assert len(offers) == 1
    assert offers[0].booking_site == "Kiwi.com"
