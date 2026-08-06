"""Nearby-airport search, deal feeds, and the Skiplagged currency handling."""
from datetime import date
from unittest.mock import Mock

import requests

from traveldeals import dealfeeds
from traveldeals.models import Mode, Offer, RoutePreference
from traveldeals.providers.base import NearbyAirportsProvider, Provider
from traveldeals.providers.geo import nearby_airports
from traveldeals.providers.skiplagged import SkiplaggedFlightProvider


def make_route(**overrides) -> RoutePreference:
    defaults = dict(id="x", origin="HAM", destination="LYS",
                    depart_date_from=date(2026, 9, 15), depart_date_until=date(2026, 9, 15))
    defaults.update(overrides)
    return RoutePreference(**defaults)


# -- nearby airports ---------------------------------------------------------

def test_nearby_airports_are_found_nearest_first():
    assert nearby_airports("HAM", 150) == [("BRE", 103), ("HAJ", 132)]


def test_radius_zero_means_off():
    assert nearby_airports("HAM", 0) == []


def test_unknown_airport_code_yields_nothing():
    assert nearby_airports("XXX", 300) == []


class PricedStub(Provider):
    """Cheap from BRE, expensive from HAM - the case the feature exists for."""
    mode = Mode.FLIGHT

    def __init__(self):
        self.searched = []

    def search(self, route):
        self.searched.append((route.origin, route.destination))
        price = 240.0 if route.origin == "HAM" else 89.0
        return [Offer(mode=Mode.FLIGHT, provider="stub",
                      booking_site=f"{route.origin}-{route.destination}",
                      price=price, currency="EUR", depart_time="2026-09-15T09:00:00",
                      arrive_time="2026-09-15T11:00:00", duration_hours=2.0)]


def test_neighbour_airports_are_searched_and_tagged():
    inner = PricedStub()
    offers = NearbyAirportsProvider(Mode.FLIGHT, inner).search(make_route(nearby_km=150))

    assert ("BRE", "LYS") in inner.searched
    cheap = next(o for o in offers if o.booking_site == "BRE-LYS")
    assert cheap.price == 89.0
    assert cheap.alt_origin == "BRE"
    assert cheap.detour_km == 103


def test_the_searched_airport_itself_is_never_tagged_as_a_detour():
    offers = NearbyAirportsProvider(Mode.FLIGHT, PricedStub()).search(make_route(nearby_km=150))
    home = [o for o in offers if o.booking_site == "HAM-LYS"]
    assert len(home) == 1
    assert not home[0].alt_origin and not home[0].alt_destination and home[0].detour_km == 0
    # ...but a different *destination* still counts as a detour, even from
    # the searched origin.
    ham_gva = next(o for o in offers if o.booking_site == "HAM-GVA")
    assert ham_gva.alt_destination == "GVA" and ham_gva.detour_km == 98


def test_without_the_option_only_the_chosen_airport_is_searched():
    inner = PricedStub()
    NearbyAirportsProvider(Mode.FLIGHT, inner).search(make_route(nearby_km=0))
    assert inner.searched == [("HAM", "LYS")]


def test_a_failing_variant_does_not_sink_the_search():
    class Flaky(PricedStub):
        def search(self, route):
            if route.origin == "BRE":
                raise RuntimeError("boom")
            return super().search(route)

    offers = NearbyAirportsProvider(Mode.FLIGHT, Flaky()).search(make_route(nearby_km=150))
    assert offers  # HAM and HAJ still came through


# -- Skiplagged currency -----------------------------------------------------

def _skiplagged_session(price_cents):
    payload = {
        "flights": {"a": [[["LH400", "HAM", "2026-09-15T09:00:00+02:00",
                             "LYS", "2026-09-15T11:00:00+02:00"]], 7200, 1, "t"]},
        "depart": [[[price_cents], [], "tok", "a"]],
        "airlines": {"LH": "Lufthansa"},
    }
    session, resp = Mock(), Mock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    session.get.return_value = resp
    return session


def test_usd_prices_are_converted_not_relabelled():
    # The API quotes USD (evidenced in the module docstring); showing 76 as
    # "76 EUR" would overstate the fare by ~14%.
    provider = SkiplaggedFlightProvider(session=_skiplagged_session(7600),
                                         rates_per_eur={"EUR": 1.0, "USD": 1.16})
    offer = provider.search(make_route())[0]
    assert offer.currency == "EUR"
    assert offer.price == 65.52


def test_itinerary_details_survive_parsing():
    provider = SkiplaggedFlightProvider(session=_skiplagged_session(7600),
                                         rates_per_eur={"EUR": 1.0, "USD": 1.16})
    offer = provider.search(make_route())[0]
    assert offer.booking_site == "Lufthansa (LH400)"
    assert offer.depart_time == "2026-09-15T09:00:00"
    assert offer.stops == 0
    assert offer.duration_hours == 2.0


def test_malformed_entry_is_skipped_rather_than_crashing():
    session, resp = Mock(), Mock()
    resp.json.return_value = {"flights": {}, "depart": [[[], [], "t", "missing"]]}
    resp.raise_for_status.return_value = None
    session.get.return_value = resp
    assert SkiplaggedFlightProvider(session=session, rates_per_eur={"EUR": 1.0}).search(make_route()) == []


# -- deal feeds --------------------------------------------------------------

RSS = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<title>Travelfree</title>
<item><title>Direct flights from Hamburg to Lyon from &#8364;39</title>
<link>https://travelfree.info/ham-lyon/</link>
<pubDate>Thu, 06 Aug 2026 10:00:00 +0000</pubDate>
<description>&lt;p&gt;Cheap &lt;b&gt;flights&lt;/b&gt; in September&lt;/p&gt;</description></item>
<item><title>Mallorca ab 29 EUR</title><link>https://travelfree.info/pmi/</link></item>
</channel></rss>"""


def _feed_session(content=RSS, status=200):
    session, resp = Mock(), Mock()
    resp.content = content
    resp.status_code = status
    resp.raise_for_status.side_effect = (requests.HTTPError("x") if status >= 400 else None)
    session.get.return_value = resp
    return session


def test_feed_items_are_parsed():
    posts = dealfeeds.fetch_feed("Travelfree", "http://x", session=_feed_session())
    assert len(posts) == 2
    assert posts[0].title.startswith("Direct flights from Hamburg to Lyon")
    assert posts[0].url == "https://travelfree.info/ham-lyon/"
    # HTML in the description is stripped, not rendered into the page.
    assert "<b>" not in posts[0].summary and "flights" in posts[0].summary


def test_only_posts_mentioning_the_route_are_surfaced():
    posts = dealfeeds.fetch_feed("Travelfree", "http://x", session=_feed_session())
    hits = dealfeeds.relevant_for(posts, "Hamburg", "Lyon")
    # An unrelated Mallorca offer is noise on a Hamburg->Lyon search.
    assert [p.url for p in hits] == ["https://travelfree.info/ham-lyon/"]


def test_no_match_returns_nothing_rather_than_random_deals():
    posts = dealfeeds.fetch_feed("Travelfree", "http://x", session=_feed_session())
    assert dealfeeds.relevant_for(posts, "Reykjavik") == []


def test_broken_feed_is_survived():
    assert dealfeeds.fetch_feed("Kaputt", "http://x", session=_feed_session(b"not xml")) == []
    assert dealfeeds.fetch_feed("Weg", "http://x", session=_feed_session(status=500)) == []
