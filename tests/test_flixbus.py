"""FlixBus provider - real bookable coach fares.

The fixture is trimmed from the live response for Berlin -> Munich on
2026-09-15 (captured through a throwaway GitHub-Actions workflow), including
the two details that are easy to get wrong: `results` is a dict keyed by trip
uid rather than a list, and the price the customer pays is
`total_with_platform_fee`, not `total`.
"""
from datetime import date

import requests

from traveldeals.models import Mode, RoutePreference
from traveldeals.providers.flixbus import FlixbusProvider

CITIES = {
    "Berlin": [{"name": "Berlin", "legacy_id": 88, "id": "40d8f682-8646-11e6-9066-549f350fcb0c"}],
    "München": [{"name": "München", "legacy_id": 94, "id": "40d901a5-8646-11e6-9066-549f350fcb0c"}],
}

TRIP = {
    "status": "available",
    "transfer_type": "Umstieg",
    "provider": "flixbus",
    "departure": {"date": "2026-09-15T07:15:00+02:00"},
    "arrival": {"date": "2026-09-15T17:35:00+02:00"},
    "duration": {"hours": 10, "minutes": 20},
    "price": {"total": 21.48, "original": 21.48, "average": 21.48,
              "total_with_platform_fee": 22.47, "average_with_platform_fee": 22.47},
    "available": {"seats": 50, "bike_slots": 0},
    "legs": [{"ride_id": "a"}, {"ride_id": "b"}],
}
SOLD_OUT = dict(TRIP, status="sold_out", price={"total": 9.99, "total_with_platform_fee": 10.99})


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
    def __init__(self, results=None, status_code=200, cities=None):
        self.results = {"uid-1": TRIP} if results is None else results
        self.status_code = status_code
        self.cities = CITIES if cities is None else cities
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, headers))
        if url.endswith("/cities"):
            return FakeResponse(self.cities.get((params or {}).get("q"), []))
        return FakeResponse({"trips": [{"results": self.results}]}, self.status_code)

    @property
    def search_calls(self):
        return [c for c in self.calls if c[0].endswith("/search")]


def make_route(**overrides) -> RoutePreference:
    defaults = dict(
        id="ber-muc", origin="Berlin", destination="München",
        depart_date_from=date(2026, 9, 15), depart_date_until=date(2026, 9, 15),
        modes=[Mode.BUS],
    )
    defaults.update(overrides)
    return RoutePreference(**defaults)


def test_real_bookable_fare_is_returned():
    offer = FlixbusProvider(session=FakeSession()).search(make_route())[0]

    assert offer.provider == "flixbus"
    assert offer.price_known is True
    assert offer.depart_time == "2026-09-15T07:15:00"
    assert offer.arrive_time == "2026-09-15T17:35:00"
    assert offer.duration_hours == 10.33
    assert offer.stops == 1  # two legs = one transfer
    assert offer.is_low_cost is True
    assert offer.details["seats_left"] == 50


def test_price_is_what_the_customer_actually_pays():
    offer = FlixbusProvider(session=FakeSession()).search(make_route())[0]

    # 21.48 is the fare, 22.47 is the total at checkout. Showing the smaller
    # one would understate the trip - the surprise this project avoids.
    assert offer.price == 22.47
    assert offer.details["fare_without_fee"] == 21.48


def test_city_uuid_is_used_not_the_numeric_legacy_id():
    session = FakeSession()
    FlixbusProvider(session=session).search(make_route())

    params = session.search_calls[0][1]
    # legacy_id 88 is rejected upstream with 'Signature "88" ... is invalid'.
    assert params["from_city_id"] == "40d8f682-8646-11e6-9066-549f350fcb0c"
    assert params["to_city_id"] == "40d901a5-8646-11e6-9066-549f350fcb0c"
    assert params["departure_date"] == "15.09.2026"


def test_results_dict_is_read_not_treated_as_a_list():
    session = FakeSession(results={"uid-1": TRIP, "uid-2": dict(TRIP, price={"total": 30.0, "total_with_platform_fee": 31.0})})
    prices = [o.price for o in FlixbusProvider(session=session).search(make_route())]
    assert sorted(prices) == [22.47, 31.0]


def test_sold_out_ride_is_not_offered():
    session = FakeSession(results={"uid-1": SOLD_OUT})
    assert FlixbusProvider(session=session).search(make_route()) == []


def test_public_api_header_is_sent():
    session = FakeSession()
    FlixbusProvider(session=session).search(make_route())
    assert session.calls[0][2]["X-API-Authentication"] == "3vJKYJVSDF9ZLcTAKX4V"


def test_booking_url_points_at_the_operator_with_the_searched_date():
    offer = FlixbusProvider(session=FakeSession()).search(make_route())[0]
    assert offer.url.startswith("https://shop.flixbus.de/search?")
    assert "rideDate=15.09.2026" in offer.url
    assert "40d8f682-8646-11e6-9066-549f350fcb0c" in offer.url


def test_unknown_city_returns_nothing_instead_of_raising():
    session = FakeSession(cities={})
    assert FlixbusProvider(session=session).search(make_route()) == []
    assert not session.search_calls  # no pointless search request either


def test_network_failure_is_survived():
    class BrokenSession(FakeSession):
        def get(self, url, params=None, headers=None, timeout=None):
            if url.endswith("/search"):
                raise requests.ConnectionError("boom")
            return super().get(url, params=params, headers=headers, timeout=timeout)

    assert FlixbusProvider(session=BrokenSession()).search(make_route()) == []


def test_request_volume_stays_bounded_on_a_wide_window():
    session = FakeSession()
    route = make_route(depart_date_from=date(2026, 9, 15), depart_date_until=date(2026, 9, 30))
    FlixbusProvider(session=session).search(route)
    # One request per day, capped - this is somebody else's backend.
    assert len(session.search_calls) == 4


# --- Bahnhofsnamen statt Städtenamen -------------------------------------
#
# Der Bus-Tab schlägt Bahnhöfe vor, FlixBus sucht Städte - und die
# Autocomplete antwortet auf alles irgendetwas. Die Antworten unten sind die
# echten, live gemessenen Trefferlisten (Wegwerf-Workflow, siehe
# Git-Historie). Ungeprüft übernommen hieß der erste Treffer: eine Suche
# Hamburg -> Köln fragte FlixBus nach Berlin -> Berlin.
LIVE_HITS = {
    "Hamburg Hbf": [{"name": "Berlin", "id": "berlin-uuid"},
                    {"name": "Hamburg", "id": "hamburg-uuid"},
                    {"name": "Flughafen Hamburg", "id": "ham-airport-uuid"}],
    "Köln Hbf": [{"name": "Berlin", "id": "berlin-uuid"},
                 {"name": "Köln", "id": "koeln-uuid"},
                 {"name": "Lincoln, NE", "id": "lincoln-uuid"}],
    "Münster(Westf) Hbf": [{"name": "Ascheberg (Westf.)", "id": "ascheberg-uuid"},
                           {"name": "Warendorf", "id": "warendorf-uuid"},
                           {"name": "Berlin", "id": "berlin-uuid"}],
    "Münster": [{"name": "Münster", "id": "muenster-uuid"},
                {"name": "Berlin", "id": "berlin-uuid"}],
    "BER": [{"name": "Berlin", "id": "berlin-uuid"},
            {"name": "Bergen", "id": "bergen-uuid"},
            {"name": "Berlin (Flughafen)", "id": "ber-airport-uuid"}],
    "Berlin": [{"name": "Berlin", "id": "berlin-uuid"}],
    "Hamburg": [{"name": "Hamburg", "id": "hamburg-uuid"}],
}


def _resolve(name: str):
    session = FakeSession(cities=LIVE_HITS)
    return FlixbusProvider(session=session)._resolve_city(name), session


def test_station_name_resolves_to_its_own_city_not_the_first_hit():
    hit, _ = _resolve("Hamburg Hbf")
    assert hit["id"] == "hamburg-uuid"  # nicht Berlin, das oben in der Liste steht


def test_second_station_name_also_skips_the_bogus_first_hit():
    hit, _ = _resolve("Köln Hbf")
    assert hit["id"] == "koeln-uuid"


def test_falls_back_to_the_bare_city_when_the_full_name_matches_nothing():
    hit, session = _resolve("Münster(Westf) Hbf")
    assert hit["id"] == "muenster-uuid"
    queried = [c[1]["q"] for c in session.calls]
    assert queried == ["Münster(Westf) Hbf", "Münster(Westf)", "Münster"]


def test_iata_code_is_translated_to_the_city():
    hit, session = _resolve("BER")
    assert hit["id"] == "berlin-uuid"  # nicht "Bergen", nicht der Flughafen
    assert session.calls[0][1]["q"] == "Berlin"


def test_plain_city_name_still_resolves_in_one_request():
    hit, session = _resolve("Berlin")
    assert hit["id"] == "berlin-uuid"
    assert len(session.calls) == 1


def test_no_match_yields_nothing_rather_than_the_wrong_city():
    # Eine Stadt, die FlixBus nicht kennt: lieber keine Buspreise als Preise
    # für eine andere Strecke.
    session = FakeSession(cities={"Kleinkleckersdorf": [{"name": "Berlin", "id": "berlin-uuid"}]})
    assert FlixbusProvider(session=session)._resolve_city("Kleinkleckersdorf") is None


def test_a_wrong_city_never_reaches_the_search_endpoint():
    session = FakeSession(cities={"Hamburg Hbf": [{"name": "Berlin", "id": "berlin-uuid"}],
                                  "Hamburg": [{"name": "Berlin", "id": "berlin-uuid"}]})
    assert FlixbusProvider(session=session).search(make_route(origin="Hamburg Hbf")) == []
    assert not session.search_calls


def test_umlaut_spelling_variants_compare_equal():
    from traveldeals.providers.flixbus import _fold_place_name

    assert _fold_place_name("München") == _fold_place_name("Muenchen")
    assert _fold_place_name("Köln") == _fold_place_name("Koeln")
    assert _fold_place_name("Halle(Saale)") == _fold_place_name("Halle (Saale)")
    # Der Flughafen ist nicht die Stadt.
    assert _fold_place_name("Berlin (Flughafen)") != _fold_place_name("Berlin")
