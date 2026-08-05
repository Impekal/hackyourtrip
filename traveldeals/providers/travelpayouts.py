"""Real flight provider: Travelpayouts (Aviasales) Data API.

Genuinely free, self-serve signup (account at travelpayouts.com -> API
token in account settings), no business agreement required - unlike Amadeus
(self-service portal decommissioned July 2026, Enterprise-only since) or
Kiwi Tequila (new integrations now need manual partner approval). See
https://support.travelpayouts.com/hc/en-us/articles/203956163

This is a cached "cheapest fare recently found" lookup, not a live GDS
search - exactly the "best price seen for this route" signal a deal-alert
bot wants, arguably a better fit here than a live search API.

Response shape has been inconsistent between the documented example and what
the live API actually returns: docs show `data: {DEST: {price, ...}}` (flat),
but real responses observed in production are one level deeper -
`data: {DEST: {"0": {price, ...}}}`, keyed by an arbitrary index. `_flatten_offers`
below handles both without assuming which one a given response uses.

Duration: when the live response includes `duration_to` (minutes, observed
in practice though not in the official docs snippet), that's used directly -
real data beats a distance guess, and unlike our own estimate it isn't
limited to non-stop offers. Only when it's absent do non-stop offers
(`transfers == 0`) fall back to the great-circle-distance estimate in
providers/geo.py; offers with a layover and no `duration_to` stay at
duration_hours=0.0 (unknown) rather than guess - the engine already treats
that the same way it treats hotel offers (max_duration_hours never rejects
them, see engine._meets_hard_constraints).

(Travelpayouts also has a GraphQL endpoint whose docs mention a
`trip_duration` field, which might be a steadier way to get this - not
implemented here because its exact query schema couldn't be verified
against real docs/testing; see README roadmap.)
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

import requests

from traveldeals.models import Mode, Offer, RoutePreference
from traveldeals.providers.base import Provider, date_candidates
from traveldeals.providers.geo import estimate_direct_flight_duration_hours

SEARCH_URL = "https://api.travelpayouts.com/v1/prices/cheap"
MAX_DATES_QUERIED = 5

# Documented Aviasales search-results deep link (named query params, not the
# fragile compact "MOW1502BKK1"-style code some older docs mention):
# https://support.travelpayouts.com/hc/en-us/articles/5711895629714
BOOKING_URL = "https://search.aviasales.com/flights/"


def _build_booking_url(route: RoutePreference, depart_time: str, return_at: str | None) -> str:
    params = {
        "origin_iata": route.origin,
        "destination_iata": route.destination,
        "depart_date": depart_time[:10],
        "adults": "1", "children": "0", "infants": "0", "trip_class": "0",
        "locale": "de",
    }
    if return_at:
        params["return_date"] = return_at[:10]
        params["one_way"] = "false"
    else:
        params["one_way"] = "true"
    return BOOKING_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())


def _flatten_offers(data: dict) -> list[dict]:
    offers = []
    for value in data.values():
        if not isinstance(value, dict):
            continue
        if "price" in value:
            offers.append(value)
        else:
            offers.extend(v for v in value.values() if isinstance(v, dict) and "price" in v)
    return offers


class TravelpayoutsFlightProvider(Provider):
    mode = Mode.FLIGHT

    def __init__(self, token: str | None = None, session: requests.Session | None = None):
        self.token = token or os.environ.get("TRAVELPAYOUTS_TOKEN")
        self.session = session or requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def search(self, route: RoutePreference) -> list[Offer]:
        if not self.configured:
            return []
        offers: list[Offer] = []
        for day in date_candidates(route)[:MAX_DATES_QUERIED]:
            try:
                offers.extend(self._search_day(route, day))
            except requests.RequestException as exc:
                print(f"[travelpayouts] request failed for {route.origin}->{route.destination} on {day}: {exc}")
        return offers

    def _search_day(self, route: RoutePreference, day: date) -> list[Offer]:
        params = {
            "origin": route.origin,
            "destination": route.destination,
            "depart_date": day.isoformat(),
            "currency": route.currency.lower(),
        }
        resp = self.session.get(SEARCH_URL, headers={"X-Access-Token": self.token}, params=params, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("success"):
            return []
        currency = payload.get("currency", route.currency).upper()
        return [self._to_offer(raw, currency, route) for raw in _flatten_offers(payload.get("data", {}))]

    def _to_offer(self, raw: dict, currency: str, route: RoutePreference) -> Offer:
        # Strip a trailing "Z" or "+HH:MM"/"-HH:MM" offset - keeps the naive
        # local-time convention used everywhere else in this codebase
        # (mock.py never produces timezone-aware strings either).
        depart_time = raw["departure_at"][:19]
        label = f"{raw.get('airline', '?')}{raw.get('flight_number', '')}"
        stops = int(raw.get("transfers", 0))

        duration_minutes = raw.get("duration_to")
        if duration_minutes is not None:
            duration_hours = round(duration_minutes / 60, 2)
            arrive_time = (datetime.fromisoformat(depart_time) + timedelta(minutes=duration_minutes)).isoformat()
        elif stops == 0 and (estimate := estimate_direct_flight_duration_hours(route.origin, route.destination)) is not None:
            duration_hours = estimate
            arrive_time = (datetime.fromisoformat(depart_time) + timedelta(hours=estimate)).isoformat()
        else:
            duration_hours = 0.0
            arrive_time = depart_time

        return Offer(
            mode=Mode.FLIGHT,
            provider="travelpayouts",
            booking_site=f"Aviasales ({label})",
            price=float(raw["price"]),
            currency=currency,
            depart_time=depart_time,
            arrive_time=arrive_time,
            duration_hours=duration_hours,
            url=_build_booking_url(route, depart_time, raw.get("return_at")),
            stops=stops,
        )
