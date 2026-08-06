"""Skiplagged flight search - the gap-filler for everything Ryanair isn't.

Ryanair only knows Ryanair, and the Travelpayouts index is a cache of fares
somebody saw recently. Skiplagged's search backend answers publicly, without
a key, and covers the *full-service* carriers neither of the other two does -
Lufthansa, Air France, KLM, Swiss, Turkish, Iberia and so on. Hamburg->Lyon,
the route that produced nothing at all before, returns 252 itineraries here.

Scope note, deliberately: Skiplagged is known for "hidden city" ticketing,
which breaks airline conditions of carriage and can cost a traveller their
frequent-flyer account. This module reads only the **regular** search
results (the `depart` list) and links to the ordinary search page. No
hidden-city itinerary is surfaced, and nothing here encourages one.

Response shape, decoded from the live service (this dev sandbox has no
internet, so it was captured through a throwaway GitHub-Actions workflow):

    {
      "flights": {                      # keyed by flight id
        "01e794b": [
          [ ["KL1756","HAM","2026-09-15T14:50:00+02:00","AMS","...T16:00:00+02:00"],
            ["KL1435","AMS","...T21:15:00+02:00","LYS","...T22:50:00+02:00"] ],
          28800,                        # total duration in seconds
          2,                            # segment count
          "<token>"
        ], ...
      },
      "depart": [ [[9100], [], "<token>", "e4089ec"], ... ],   # price in cents + flight id
      "airlines": {"KL": "KLM", ...}, "airports": {...}, "cities": {...}
    }
"""
from __future__ import annotations

from datetime import datetime

import requests

from traveldeals.models import Mode, Offer, RoutePreference
from traveldeals.providers.base import Provider, date_candidates

SEARCH_URL = "https://skiplagged.com/api/search.php"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

# One request per travel day; the endpoint takes a single departure date.
MAX_DAYS_QUERIED = 3
# Even a thin route returns hundreds of itineraries, and the engine ranks
# them anyway - keeping the cheapest slice keeps memory and render time sane.
MAX_OFFERS_PER_DAY = 40

BOOKING_BASE = "https://skiplagged.com/flights"


def _build_booking_url(route: RoutePreference, day: str) -> str:
    """Ordinary search page for the route - not a hidden-city deep link."""
    return f"{BOOKING_BASE}/{route.origin}/{route.destination}/{day}"


class SkiplaggedFlightProvider(Provider):
    mode = Mode.FLIGHT

    def __init__(self, session: requests.Session | None = None, currency: str = "EUR"):
        self.session = session or requests.Session()
        # The API echoes no currency field, so it is pinned via the request
        # instead of guessed from the number - a 91 that is actually dollars
        # displayed as euros would be exactly the kind of wrong price this
        # project refuses to show.
        self.currency = currency.upper()

    @property
    def configured(self) -> bool:
        return True

    def search(self, route: RoutePreference) -> list[Offer]:
        offers: list[Offer] = []
        for day in date_candidates(route)[:MAX_DAYS_QUERIED]:
            offers.extend(self._search_day(route, day.isoformat()))
        return offers

    def _search_day(self, route: RoutePreference, day: str) -> list[Offer]:
        try:
            resp = self.session.get(SEARCH_URL, params={
                "from": route.origin, "to": route.destination, "depart": day,
                "return": "", "poll": "true", "sort": "cost",
                "currency": self.currency,
            }, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            print(f"[skiplagged] request failed for {route.origin}->{route.destination} on {day}: {exc}")
            return []
        except ValueError:
            return []

        flights = payload.get("flights") or {}
        airlines = payload.get("airlines") or {}
        offers = []
        for entry in (payload.get("depart") or [])[:MAX_OFFERS_PER_DAY]:
            offer = self._to_offer(entry, flights, airlines, route, day)
            if offer is not None:
                offers.append(offer)
        return offers

    def _to_offer(self, entry, flights: dict, airlines: dict,
                   route: RoutePreference, day: str) -> Offer | None:
        # entry: [[price_cents], [], token, flight_id]
        try:
            price_cents = entry[0][0]
            flight_id = entry[3]
        except (IndexError, TypeError):
            return None
        flight = flights.get(flight_id)
        if not flight or price_cents is None:
            return None

        try:
            segments, duration_seconds = flight[0], flight[1]
            first, last = segments[0], segments[-1]
            depart_time, arrive_time = first[2], last[4]
        except (IndexError, TypeError):
            return None

        flight_number = first[0] or ""
        carrier = flight_number[:2]
        airline_name = airlines.get(carrier, carrier or "Airline")
        return Offer(
            mode=Mode.FLIGHT,
            provider="skiplagged",
            booking_site=f"{airline_name} ({flight_number})",
            price=round(price_cents / 100, 2),
            currency=self.currency,
            # Strip the offset, matching the naive-local convention used
            # everywhere else in this codebase.
            depart_time=depart_time[:19],
            arrive_time=arrive_time[:19],
            duration_hours=round((duration_seconds or 0) / 3600, 2),
            url=_build_booking_url(route, day),
            stops=max(len(segments) - 1, 0),
            line_label=" → ".join(str(seg[0]) for seg in segments if seg),
        )
