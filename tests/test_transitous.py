"""Transitous provider + the engine's handling of price-less offers.

The response fixtures below are trimmed copies of what the live service
actually returned for Berlin Hbf -> München Hbf (captured through a throwaway
GitHub Actions workflow, since the dev sandbox has no internet), so the
parsing is tested against real field names and real UTC timestamps.
"""
import json
from datetime import date

import pytest
import requests

from traveldeals.engine import DealEngine
from traveldeals.models import Mode, Offer, Priority, RoutePreference
from traveldeals.pricehistory import PriceHistory
from traveldeals.providers.base import Provider
from traveldeals.providers.transitous import (TransitousBusProvider,
                                               TransitousTrainProvider,
                                               _local_anchor_to_utc,
                                               _to_local_naive)

GEOCODE_BERLIN = [
    {"type": "PLACE", "category": "hostel_16", "name": "A&O Berlin Hauptbahnhof",
     "id": "way/[423971811]", "lat": 52.52, "lon": 13.36, "country": "DE", "tz": "Europe/Berlin"},
    {"type": "STOP", "name": "Berlin Hauptbahnhof", "id": "stop-berlin-hbf",
     "lat": 52.52498, "lon": 13.369114, "country": "DE", "tz": "Europe/Berlin"},
]
GEOCODE_MUNICH = [
    {"type": "PLACE", "category": "sauna_14", "name": "Herrensauna am Hauptbahnhof",
     "id": "node/[4369294190]", "country": "DE", "tz": "Europe/Berlin"},
    {"type": "STOP", "name": "München Hbf", "id": "stop-muenchen-hbf",
     "country": "DE", "tz": "Europe/Berlin"},
]

ICE_ITINERARY = {
    "duration": 14940,
    "startTime": "2026-09-15T08:37:00Z",   # 10:37 local
    "endTime": "2026-09-15T12:46:00Z",     # 14:46 local
    "transfers": 0,
    "legs": [{
        "mode": "HIGHSPEED_RAIL",
        "displayName": "ICE 1007",
        "agencyName": "DB Fernverkehr AG",
        "realTime": True,
        "from": {"name": "S+U Berlin Hauptbahnhof", "track": "4", "tz": "Europe/Berlin"},
        "to": {"name": "München Hbf", "track": "22", "tz": "Europe/Berlin"},
    }],
}
WALK_ONLY_ITINERARY = {
    "duration": 900,
    "startTime": "2026-09-15T08:00:00Z",
    "endTime": "2026-09-15T08:15:00Z",
    "transfers": 0,
    "legs": [{"mode": "WALK", "from": {"name": "A"}, "to": {"name": "B"}}],
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
    def __init__(self, itineraries=None, geocode=None):
        self.itineraries = [ICE_ITINERARY] if itineraries is None else itineraries
        self.geocode = geocode
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params))
        if url.endswith("/geocode"):
            if self.geocode is not None:
                return FakeResponse(self.geocode)
            text = (params or {}).get("text", "")
            return FakeResponse(GEOCODE_MUNICH if "ünchen" in text or "unchen" in text else GEOCODE_BERLIN)
        return FakeResponse({"itineraries": self.itineraries})

    @property
    def plan_calls(self):
        return [c for c in self.calls if c[0].endswith("/plan")]


def make_route(**overrides) -> RoutePreference:
    defaults = dict(
        id="bln-muc", origin="Berlin Hauptbahnhof", destination="München Hbf",
        depart_date_from=date(2026, 9, 15), depart_date_until=date(2026, 9, 15),
        modes=[Mode.TRAIN],
    )
    defaults.update(overrides)
    return RoutePreference(**defaults)


# -- time conversion ---------------------------------------------------------

def test_utc_response_time_becomes_local_naive():
    # 08:37 UTC in September is 10:37 in Berlin (CEST) - a train the user sees
    # as departing at 10:37 must not show up as 08:37.
    assert _to_local_naive("2026-09-15T08:37:00Z", "Europe/Berlin") == "2026-09-15T10:37:00"


def test_unknown_timezone_falls_back_to_utc_instead_of_raising():
    assert _to_local_naive("2026-09-15T08:37:00Z", "Mars/Olympus") == "2026-09-15T08:37:00"


def test_local_anchor_is_sent_as_utc():
    # 06:00 local in Berlin (CEST) is 04:00 UTC.
    assert _local_anchor_to_utc(date(2026, 9, 15), "06:00", "Europe/Berlin") == "2026-09-15T04:00:00Z"


# -- provider ----------------------------------------------------------------

def test_offers_carry_no_price_and_say_so():
    session = FakeSession()
    offers = TransitousTrainProvider(session=session).search(make_route())

    assert offers, "expected at least one connection"
    for offer in offers:
        assert offer.price_known is False
        assert offer.price == 0.0


def test_offer_keeps_the_real_line_operator_and_times():
    offers = TransitousTrainProvider(session=FakeSession()).search(make_route())
    offer = offers[0]

    assert offer.line_label == "ICE 1007"
    assert offer.booking_site == "DB Fernverkehr AG"
    assert offer.depart_time == "2026-09-15T10:37:00"
    assert offer.arrive_time == "2026-09-15T14:46:00"
    assert offer.duration_hours == 4.15
    assert offer.stops == 0
    assert offer.details["track"] == "4"
    # No booking URL exists for a MOTIS itinerary - better empty than fake.
    assert offer.url == ""


def test_only_stops_are_routed_not_hotels_or_saunas():
    session = FakeSession()
    TransitousTrainProvider(session=session).search(make_route())

    from_place = session.plan_calls[0][1]["fromPlace"]
    to_place = session.plan_calls[0][1]["toPlace"]
    assert from_place == "stop-berlin-hbf"
    assert to_place == "stop-muenchen-hbf"


def test_identical_connection_from_overlapping_anchors_appears_once():
    # All three daily anchors return the same ICE; it must not be listed 3x.
    offers = TransitousTrainProvider(session=FakeSession()).search(make_route())
    assert len(offers) == 1


def test_walk_only_itinerary_is_not_a_train_offer():
    session = FakeSession(itineraries=[WALK_ONLY_ITINERARY])
    assert TransitousTrainProvider(session=session).search(make_route()) == []


def test_departure_outside_the_requested_days_is_dropped():
    session = FakeSession()
    route = make_route(depart_date_from=date(2026, 9, 16), depart_date_until=date(2026, 9, 16))
    assert TransitousTrainProvider(session=session).search(route) == []


def test_unresolvable_place_returns_nothing_instead_of_raising():
    session = FakeSession(geocode=[{"type": "PLACE", "name": "Nur ein Hotel", "id": "way/[1]"}])
    assert TransitousTrainProvider(session=session).search(make_route()) == []


def test_network_failure_is_survived():
    class BrokenSession(FakeSession):
        def get(self, url, params=None, headers=None, timeout=None):
            if url.endswith("/plan"):
                raise requests.ConnectionError("boom")
            return super().get(url, params=params, headers=headers, timeout=timeout)

    assert TransitousTrainProvider(session=BrokenSession()).search(make_route()) == []


def test_bus_provider_asks_for_coaches_and_ignores_trains():
    session = FakeSession()
    TransitousBusProvider(session=session).search(make_route(modes=[Mode.BUS]))
    assert "COACH" in session.plan_calls[0][1]["transitModes"]
    # The fixture only contains an ICE, which is not a coach journey.
    assert TransitousBusProvider(session=FakeSession()).search(make_route(modes=[Mode.BUS])) == []


def test_request_volume_stays_bounded_on_a_wide_window():
    session = FakeSession()
    route = make_route(depart_date_from=date(2026, 9, 15), depart_date_until=date(2026, 9, 30))
    TransitousTrainProvider(session=session).search(route)
    # MAX_DAYS_QUERIED (4) x DEPART_ANCHORS (3). This talks to a free
    # volunteer-run service - a two-week window must not become 45 requests.
    assert len(session.plan_calls) == 12


# -- engine handling of price-less offers ------------------------------------

class StubProvider(Provider):
    def __init__(self, mode, offers):
        self.mode = mode
        self._offers = offers

    def search(self, route):
        return list(self._offers)


def priced_offer(price, mode=Mode.TRAIN, hour=9) -> Offer:
    return Offer(mode=mode, provider="stub", booking_site="Anbieter", price=price, currency="EUR",
                 depart_time=f"2026-09-15T{hour:02d}:00:00", arrive_time=f"2026-09-15T{hour + 4:02d}:00:00",
                 duration_hours=4.0)


def priceless_offer(mode=Mode.TRAIN, hour=10) -> Offer:
    return Offer(mode=mode, provider="transitous", booking_site="DB Fernverkehr AG", price=0.0,
                 price_known=False, line_label="ICE 1007", currency="EUR",
                 depart_time=f"2026-09-15T{hour:02d}:00:00", arrive_time=f"2026-09-15T{hour + 4:02d}:00:00",
                 duration_hours=4.0)


@pytest.fixture
def engine_factory(tmp_path):
    def build(offers, mode=Mode.TRAIN):
        return DealEngine({mode: StubProvider(mode, offers)},
                          PriceHistory(tmp_path / "history.json"), use_live_currency=False)
    return build


def test_priceless_option_never_ranks_as_the_cheapest(engine_factory):
    engine = engine_factory([priceless_offer(), priced_offer(59.0), priced_offer(120.0)])
    options = engine.search(make_route(priority=Priority.CHEAPEST))

    # Its total_price of 0.0 is a placeholder; sorting it first would present
    # an unknown fare as a free trip.
    assert [o.total_price for o in options] == [59.0, 120.0, 0.0]
    assert options[-1].has_unknown_price


def test_priceless_option_is_never_a_deal(engine_factory):
    engine = engine_factory([priceless_offer(), *[priced_offer(200.0, hour=h) for h in (7, 8, 9, 11)]])
    options = engine.search(make_route())

    priceless = [o for o in options if o.has_unknown_price]
    assert priceless and not priceless[0].is_deal


def test_deals_only_search_excludes_priceless_options(engine_factory):
    offers = [priceless_offer(), priced_offer(50.0, hour=7), priced_offer(200.0, hour=8),
              priced_offer(210.0, hour=11), priced_offer(220.0, hour=13)]
    options = engine_factory(offers).search(make_route(deals_only=True))

    assert options, "the 50 EUR offer is well below the median and should survive"
    assert all(not o.has_unknown_price for o in options)


def test_priceless_option_does_not_drag_the_median_down(engine_factory):
    # Without excluding the 0.0 placeholder the median collapses and the
    # genuinely cheap 100 EUR offer would stop counting as a deal.
    offers = [priceless_offer(), priced_offer(100.0, hour=7), priced_offer(200.0, hour=8),
              priced_offer(210.0, hour=11), priced_offer(220.0, hour=13)]
    options = engine_factory(offers).search(make_route())

    cheapest = min(options, key=lambda o: (o.has_unknown_price, o.total_price))
    assert cheapest.total_price == 100.0
    assert cheapest.is_below_median


def test_budget_does_not_silently_hide_a_connection_with_no_price(engine_factory):
    options = engine_factory([priceless_offer(), priced_offer(500.0)]).search(make_route(budget=100))

    assert [o.has_unknown_price for o in options] == [True]


def test_priceless_option_gets_an_explanatory_note_not_a_savings_hint(engine_factory):
    engine = engine_factory([priceless_offer(), priced_offer(80.0, hour=7)])
    option = next(o for o in engine.search(make_route()) if o.has_unknown_price)

    assert len(option.recommendations) == 1
    assert "ICE 1007" in option.recommendations[0]
    assert "Preis" in option.recommendations[0]
    # No money talk: no savings, no currency conversion, no deal claim.
    assert "spart" not in option.recommendations[0]


def test_priceless_price_is_not_written_to_the_price_history(engine_factory, tmp_path):
    history = PriceHistory(tmp_path / "history.json")
    engine = DealEngine({Mode.TRAIN: StubProvider(Mode.TRAIN, [priceless_offer(), priced_offer(88.0)])},
                        history, use_live_currency=False)
    engine.search(make_route())
    history.save()

    recorded = [entry["price"] for entries in
                json.loads((tmp_path / "history.json").read_text()).values()
                for mode_entries in entries.values() for entry in mode_entries]
    # A recorded 0.0 would poison every future "is this a price drop?" and
    # "is this an error fare?" check for this route.
    assert recorded == [88.0]
