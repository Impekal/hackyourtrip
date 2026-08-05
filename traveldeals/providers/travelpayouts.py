"""Real flight provider: Travelpayouts (Aviasales) Data API.

Genuinely free, self-serve signup (account at travelpayouts.com -> API
token in account settings), no business agreement required - unlike Amadeus
(self-service portal decommissioned July 2026, Enterprise-only since) or
Kiwi Tequila (new integrations now need manual partner approval). See
https://support.travelpayouts.com/hc/en-us/articles/203956163

Two endpoints are queried and merged, both **per month** rather than per
day. That detail matters more than anything else here: measured against the
live API (via a throwaway GitHub-Actions workflow, since this dev sandbox
has no internet), asking `prices_for_dates` for one specific date returns
exactly **1** offer, while asking for the whole month returns **27-44**.
Querying per month and filtering the results down to the wanted dates is
therefore what actually produces a full result list; the previous
one-request-per-date approach against `v1/prices/cheap` structurally could
not return more than one offer per date, which is why searches looked so
empty.

- `aviasales/v3/prices_for_dates` - the richer of the two: every row has a
  real per-itinerary booking `link` (deep-links to that exact flight) and
  the actual booking `gate` (Kiwi.com, Trip.com, Biletix, ...).
- `v2/prices/latest` - a separate index that surfaces partly *different*
  itineraries, so merging it in widens coverage. No per-itinerary link, so
  those rows fall back to a generic search URL. One-way only: with
  `one_way=false` this endpoint returned zero rows in testing, so it is
  skipped entirely for round trips.

Both are cached "fares recently found" indexes rather than a live GDS
search, so this cannot match a metasearch engine's live inventory - but it
is the fullest view the free tier offers, and it is exactly the "best price
seen for this route" signal a deal-alert bot wants.

Duration: the response includes `duration_to` (minutes for the outbound
leg), which is used directly - real data beats a distance guess, and unlike
our own estimate it isn't limited to non-stop offers. Only when it's absent
do non-stop offers (`transfers == 0`) fall back to the great-circle-distance
estimate in providers/geo.py; offers with a layover and no `duration_to`
stay at duration_hours=0.0 (unknown) rather than guess - the engine already
treats that the same way it treats hotel offers (max_duration_hours never
rejects them, see engine._meets_hard_constraints).
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

import requests

from traveldeals.models import Mode, Offer, RoutePreference
from traveldeals.providers.base import Provider, date_candidates
from traveldeals.providers.geo import estimate_direct_flight_duration_hours

SEARCH_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
LATEST_URL = "https://api.travelpayouts.com/v2/prices/latest"

# Safety valve on a very wide date range: at most this many month-requests
# per endpoint. A month is one request and covers ~30 candidate days, so
# even a long window stays cheap.
MAX_MONTHS_QUERIED = 6
OFFERS_PER_REQUEST = 1000

# Absolute base for the relative `link` the API returns
# ("/search/BER1809BCN1?t=..."), which points at the exact itinerary rather
# than a generic search form.
AVIASALES_BASE = "https://www.aviasales.com"

# Fallback only, for responses that somehow carry no `link`: the documented
# named-param search URL. https://support.travelpayouts.com/hc/en-us/articles/5711895629714
BOOKING_URL = "https://search.aviasales.com/flights/"


def _months_covering(route: RoutePreference) -> list[str]:
    """Distinct "YYYY-MM" months the candidate departure dates fall into,
    in order - one API request each, rather than one per day."""
    months: list[str] = []
    for day in date_candidates(route):
        month = day.strftime("%Y-%m")
        if month not in months:
            months.append(month)
    return months


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
        wanted_days = {d.isoformat() for d in date_candidates(route)}
        round_trip = bool(route.round_trip and route.return_date)

        offers: list[Offer] = []
        seen: set[tuple] = set()
        for month in _months_covering(route)[:MAX_MONTHS_QUERIED]:
            fetchers = [self._fetch_prices_for_dates]
            # v2/prices/latest returns nothing for round trips (verified
            # against the live API), so don't waste a request on it there.
            if not round_trip:
                fetchers.append(self._fetch_latest)
            for fetch in fetchers:
                try:
                    found = fetch(route, month, round_trip)
                except requests.RequestException as exc:
                    print(f"[travelpayouts] request failed for {route.origin}->{route.destination} in {month}: {exc}")
                    continue
                for offer in found:
                    # Only keep departures the user actually asked for - the
                    # month query deliberately over-fetches, the flex window
                    # decides what counts.
                    if offer.depart_time[:10] not in wanted_days:
                        continue
                    # The two endpoints overlap, and the same itinerary can
                    # repeat; keep the first (cheapest, since sorting=price).
                    key = (offer.depart_time, offer.booking_site, offer.price)
                    if key in seen:
                        continue
                    seen.add(key)
                    offers.append(offer)
        return offers

    def _fetch_prices_for_dates(self, route: RoutePreference, month: str, round_trip: bool) -> list[Offer]:
        params = {
            "origin": route.origin,
            "destination": route.destination,
            "departure_at": month,
            "currency": route.currency.lower(),
            "limit": OFFERS_PER_REQUEST,
            "sorting": "price",
            "one_way": "false" if round_trip else "true",
        }
        if round_trip:
            # A specific return_at date returned zero rows in testing, while
            # the return *month* works - and with a return leg priced in,
            # `price` is already the combined total for both legs.
            params["return_at"] = route.return_date.strftime("%Y-%m")
        payload = self._get(SEARCH_URL, params)
        if payload is None:
            return []
        currency = (payload.get("currency") or route.currency).upper()
        return [self._to_offer(raw, currency, route) for raw in payload.get("data", []) if raw.get("price")]

    def _fetch_latest(self, route: RoutePreference, month: str, round_trip: bool) -> list[Offer]:
        params = {
            "origin": route.origin,
            "destination": route.destination,
            "currency": route.currency.lower(),
            "limit": OFFERS_PER_REQUEST,
            "sorting": "price",
            "one_way": "true",
            "period_type": "month",
            "beginning_of_period": f"{month}-01",
        }
        payload = self._get(LATEST_URL, params)
        if payload is None:
            return []
        currency = (payload.get("currency") or route.currency).upper()
        return [self._latest_to_offer(raw, currency, route) for raw in payload.get("data", []) if raw.get("value")]

    def _get(self, url: str, params: dict) -> dict | None:
        resp = self.session.get(url, headers={"X-Access-Token": self.token}, params=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        return None if not payload.get("success", True) else payload

    def _latest_to_offer(self, raw: dict, currency: str, route: RoutePreference) -> Offer:
        """v2/prices/latest rows: date-only (no clock time), price in
        `value`, stops in `number_of_changes`, total minutes in `duration`,
        and no per-itinerary link."""
        depart_time = f"{raw['depart_date']}T00:00:00"
        stops = int(raw.get("number_of_changes", 0) or 0)
        minutes = raw.get("duration")
        if minutes:
            duration_hours = round(minutes / 60, 2)
            arrive_time = (datetime.fromisoformat(depart_time) + timedelta(minutes=minutes)).isoformat()
        else:
            duration_hours, arrive_time = 0.0, depart_time
        return Offer(
            mode=Mode.FLIGHT,
            provider="travelpayouts",
            booking_site=raw.get("gate") or "Aviasales",
            price=float(raw["value"]),
            currency=currency,
            depart_time=depart_time,
            arrive_time=arrive_time,
            duration_hours=duration_hours,
            url=_build_booking_url(route, depart_time, None),
            stops=stops,
        )

    def _to_offer(self, raw: dict, currency: str, route: RoutePreference) -> Offer:
        # Strip a trailing "Z" or "+HH:MM"/"-HH:MM" offset - keeps the naive
        # local-time convention used everywhere else in this codebase
        # (mock.py never produces timezone-aware strings either).
        depart_time = raw["departure_at"][:19]
        label = f"{raw.get('airline', '?')}{raw.get('flight_number', '')}"
        gate = raw.get("gate") or "Aviasales"
        stops = int(raw.get("transfers", 0) or 0)

        duration_minutes = raw.get("duration_to")
        if duration_minutes:
            duration_hours = round(duration_minutes / 60, 2)
            arrive_time = (datetime.fromisoformat(depart_time) + timedelta(minutes=duration_minutes)).isoformat()
        elif stops == 0 and (estimate := estimate_direct_flight_duration_hours(route.origin, route.destination)) is not None:
            duration_hours = estimate
            arrive_time = (datetime.fromisoformat(depart_time) + timedelta(hours=estimate)).isoformat()
        else:
            duration_hours = 0.0
            arrive_time = depart_time

        return_at = raw.get("return_at")
        link = raw.get("link")
        return Offer(
            mode=Mode.FLIGHT,
            provider="travelpayouts",
            booking_site=f"{gate} ({label})",
            price=float(raw["price"]),
            currency=currency,
            depart_time=depart_time,
            arrive_time=arrive_time,
            duration_hours=duration_hours,
            # The per-itinerary link goes straight to this exact flight;
            # only fall back to the generic search URL if it's missing.
            url=(AVIASALES_BASE + link) if link else _build_booking_url(route, depart_time, return_at),
            stops=stops,
            return_depart_time=return_at[:19] if return_at else None,
        )
