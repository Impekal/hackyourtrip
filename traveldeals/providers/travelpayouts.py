"""Real flight provider: Travelpayouts (Aviasales) Data API.

Genuinely free, self-serve signup (account at travelpayouts.com -> API
token in account settings), no business agreement required - unlike Amadeus
(self-service portal decommissioned July 2026, Enterprise-only since) or
Kiwi Tequila (new integrations now need manual partner approval). See
https://support.travelpayouts.com/hc/en-us/articles/203956163

This is a cached "cheapest fare recently found" lookup, not a live GDS
search - exactly the "best price seen for this route" signal a deal-alert
bot wants, arguably a better fit here than a live search API. Trade-off:
the response gives price/airline/stops/departure time but no arrival time
or flight duration.

For non-stop offers (transfers == 0), duration is estimated from the
great-circle distance between the two airports (see providers/geo.py) - a
reasonable approximation when there's no layover to account for. For
connecting offers, the layover length has nothing to do with that distance,
so duration stays unknown (0.0) rather than guess - the engine already
treats a duration of 0 the same way it treats hotel offers
(max_duration_hours never rejects them, see engine._meets_hard_constraints),
so this degrades gracefully rather than needing special-casing.

(Travelpayouts also has a GraphQL endpoint whose docs mention a
`trip_duration` field covering connections too, which would remove this
limitation - not implemented here because its exact query schema couldn't
be verified against real docs/testing; see README roadmap.)
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
        return [self._to_offer(raw, currency, route) for raw in payload.get("data", {}).values()]

    def _to_offer(self, raw: dict, currency: str, route: RoutePreference) -> Offer:
        depart_time = raw["departure_at"].rstrip("Z")
        label = f"{raw.get('airline', '?')}{raw.get('flight_number', '')}"
        stops = int(raw.get("transfers", 0))

        duration_hours = 0.0
        arrive_time = depart_time
        if stops == 0:
            estimate = estimate_direct_flight_duration_hours(route.origin, route.destination)
            if estimate is not None:
                duration_hours = estimate
                arrive_time = (datetime.fromisoformat(depart_time) + timedelta(hours=estimate)).isoformat()

        return Offer(
            mode=Mode.FLIGHT,
            provider="travelpayouts",
            booking_site=f"Aviasales ({label})",
            price=float(raw["price"]),
            currency=currency,
            depart_time=depart_time,
            arrive_time=arrive_time,
            duration_hours=duration_hours,
            url="https://www.aviasales.com",
            stops=stops,
        )
