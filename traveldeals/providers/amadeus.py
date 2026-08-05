"""Real flight provider: Amadeus Self-Service Flight Offers Search API.

Free "test" environment, no cost, but a request quota - see
https://developers.amadeus.com (sign up, create an app, copy the API Key/
Secret into AMADEUS_API_KEY/AMADEUS_API_SECRET). Test-environment data is
Amadeus's own cached sample inventory, not live production fares, but the
integration itself - OAuth2, request/response shape, error handling - is the
real thing, unlike providers/mock.py.

The flight-offers-search endpoint takes one departureDate per call (no date
range), so a route with flex_days_before/after fans out into one HTTP call
per candidate day - MAX_DATES_QUERIED caps that fan-out so a wide flex
window can't blow through the free-tier quota in a single `check` run.
"""
from __future__ import annotations

import os
import re
from datetime import date, timedelta

import requests

from traveldeals.models import Mode, Offer, RoutePreference
from traveldeals.providers.base import Provider, date_candidates

TOKEN_URL = "https://test.api.amadeus.com/v1/security/oauth2/token"
SEARCH_URL = "https://test.api.amadeus.com/v2/shopping/flight-offers"
MAX_DATES_QUERIED = 5

_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?")


def _parse_duration_hours(iso8601_duration: str) -> float:
    """'PT2H30M' -> 2.5. Amadeus always returns this format for itineraries."""
    m = _DURATION_RE.match(iso8601_duration)
    if not m:
        return 0.0
    hours, minutes = (int(g) if g else 0 for g in m.groups())
    return round(hours + minutes / 60, 2)


class AmadeusFlightProvider(Provider):
    mode = Mode.FLIGHT

    def __init__(self, api_key: str | None = None, api_secret: str | None = None,
                 session: requests.Session | None = None):
        self.api_key = api_key or os.environ.get("AMADEUS_API_KEY")
        self.api_secret = api_secret or os.environ.get("AMADEUS_API_SECRET")
        self.session = session or requests.Session()
        self._token: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def search(self, route: RoutePreference) -> list[Offer]:
        if not self.configured:
            return []
        offers: list[Offer] = []
        for day in date_candidates(route)[:MAX_DATES_QUERIED]:
            try:
                offers.extend(self._search_day(route, day))
            except requests.RequestException as exc:
                print(f"[amadeus] request failed for {route.origin}->{route.destination} on {day}: {exc}")
        return offers

    def _get_token(self, force_refresh: bool = False) -> str:
        if self._token and not force_refresh:
            return self._token
        resp = self.session.post(TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.api_secret,
        }, timeout=10)
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    def _search_day(self, route: RoutePreference, day: date) -> list[Offer]:
        token = self._get_token()
        params = {
            "originLocationCode": route.origin,
            "destinationLocationCode": route.destination,
            "departureDate": day.isoformat(),
            "adults": 1,
            "currencyCode": route.currency,
            "max": 15,
        }
        resp = self.session.get(SEARCH_URL, headers={"Authorization": f"Bearer {token}"},
                                 params=params, timeout=15)
        if resp.status_code == 401:
            token = self._get_token(force_refresh=True)
            resp = self.session.get(SEARCH_URL, headers={"Authorization": f"Bearer {token}"},
                                     params=params, timeout=15)
        resp.raise_for_status()
        return [self._to_offer(raw, route) for raw in resp.json().get("data", [])]

    def _to_offer(self, raw: dict, route: RoutePreference) -> Offer:
        itinerary = raw["itineraries"][0]
        segments = itinerary["segments"]
        first_segment, last_segment = segments[0], segments[-1]
        carrier = raw.get("validatingAirlineCodes", [segments[0]["carrierCode"]])[0]

        fare_details = raw.get("travelerPricings", [{}])[0].get("fareDetailsBySegment", [{}])[0]
        included_bags = fare_details.get("includedCheckedBags", {}).get("quantity", 0)
        # Amadeus doesn't return a bag fee directly for excluded baggage; a
        # flat estimate is a reasonable placeholder until a real ancillary-
        # pricing call is added.
        checked_bag_fee = 0.0 if included_bags > 0 else 35.0

        return Offer(
            mode=Mode.FLIGHT,
            provider="amadeus",
            booking_site=f"Amadeus ({carrier})",
            price=float(raw["price"]["total"]),
            currency=raw["price"]["currency"],
            depart_time=first_segment["departure"]["at"],
            arrive_time=last_segment["arrival"]["at"],
            duration_hours=_parse_duration_hours(itinerary["duration"]),
            url="https://amadeus.com",
            checked_bag_fee=checked_bag_fee,
            is_low_cost=False,
            stops=len(segments) - 1,
        )
