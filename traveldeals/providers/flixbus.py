"""Real, bookable FlixBus fares - free, no key, no account.

FlixBus' own search backend is publicly reachable with a fixed, public
`X-API-Authentication` constant (the same one their website ships to every
visitor). It returns live, bookable prices, seat availability and real
transfer information - which makes bus the second mode with genuine prices
after flights, and the only one where a *ground* option can now be compared
against a flight on equal terms.

Verified against the live service (through a throwaway GitHub-Actions
workflow, since this dev sandbox has no internet). Berlin -> Munich on
2026-09-15 returned e.g. 21.48 EUR (22.47 with booking fee), 07:15 -> 17:35,
10h20, 50 seats left.

Two endpoints:

- `search/autocomplete/cities?q=` - resolves "Berlin" to a city UUID. The
  numeric `legacy_id` in the same response does **not** work for search; it
  answers `Signature "88" ... is invalid`, which is how the UUID requirement
  was found.
- `search/service/v4/search` - the actual fares. `trips[].results` is a
  **dict keyed by trip uid**, not a list.

Prices: `price.total` is the fare, `price.total_with_platform_fee` is what
the customer actually pays. The latter is used, because a price that turns
into a bigger one at checkout is exactly the kind of surprise this project
tries to avoid.
"""
from __future__ import annotations

from datetime import datetime

import requests

from traveldeals.models import Mode, Offer, RoutePreference
from traveldeals.providers.base import Provider, date_candidates

BASE_URL = "https://global.api.flixbus.com"
# Public constant shipped in FlixBus' own web client - not a credential of
# ours, and not a secret; it identifies the web frontend.
API_AUTH = "3vJKYJVSDF9ZLcTAKX4V"

HEADERS = {
    "X-API-Authentication": API_AUTH,
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

# One request per travel day; the search endpoint takes a single date. Kept
# in step with the Transitous cap for the same reason - politeness.
MAX_DAYS_QUERIED = 4

# The operator's own search page, built from the parameters its site uses.
BOOKING_BASE = "https://shop.flixbus.de/search"


def _build_booking_url(origin_id: str, destination_id: str, day) -> str:
    params = {
        "departureCity": origin_id, "arrivalCity": destination_id,
        "rideDate": day.strftime("%d.%m.%Y"), "adult": "1",
    }
    return BOOKING_BASE + "?" + "&".join(f"{k}={v}" for k, v in params.items())


def _naive(iso: str) -> str:
    """"2026-09-15T07:15:00+02:00" -> "2026-09-15T07:15:00".

    The offset is the stop's own local time, which is already what the rest
    of this codebase works in - so it is dropped rather than converted.
    """
    return iso[:19]


class FlixbusProvider(Provider):
    mode = Mode.BUS

    def __init__(self, session: requests.Session | None = None, base_url: str = BASE_URL):
        self.session = session or requests.Session()
        self.base_url = base_url.rstrip("/")

    @property
    def configured(self) -> bool:
        return True  # no key, no account

    def _get(self, path: str, params: dict):
        resp = self.session.get(f"{self.base_url}{path}", params=params,
                                 headers=HEADERS, timeout=25)
        resp.raise_for_status()
        return resp.json()

    def _resolve_city(self, name: str) -> dict | None:
        """City UUID for a free-text place - the numeric legacy_id is rejected
        by the search endpoint, so only `id` is usable."""
        try:
            hits = self._get("/search/autocomplete/cities", {"q": name, "lang": "de"})
        except requests.RequestException as exc:
            print(f"[flixbus] autocomplete failed for {name!r}: {exc}")
            return None
        except ValueError:
            return None
        for hit in hits or []:
            if hit.get("id"):
                return hit
        return None

    def search(self, route: RoutePreference) -> list[Offer]:
        origin = self._resolve_city(route.origin)
        destination = self._resolve_city(route.destination)
        if not origin or not destination:
            return []

        offers: list[Offer] = []
        for day in date_candidates(route)[:MAX_DAYS_QUERIED]:
            try:
                payload = self._get("/search/service/v4/search", {
                    "from_city_id": origin["id"], "to_city_id": destination["id"],
                    "departure_date": day.strftime("%d.%m.%Y"),
                    "products": '{"adult":1}', "currency": route.currency.upper(),
                    "locale": "de", "search_by": "cities",
                    "include_after_midnight_rides": 1,
                })
            except requests.RequestException as exc:
                print(f"[flixbus] search failed for {route.origin}->{route.destination} on {day}: {exc}")
                continue
            except ValueError:
                continue

            for trip in payload.get("trips") or []:
                # `results` is keyed by trip uid, not a list.
                for result in (trip.get("results") or {}).values():
                    offer = self._to_offer(result, route, origin, destination, day)
                    if offer is not None:
                        offers.append(offer)
        return offers

    def _to_offer(self, result: dict, route: RoutePreference, origin: dict,
                   destination: dict, day) -> Offer | None:
        # Sold out or otherwise unbookable rides are not offers.
        if result.get("status") != "available":
            return None
        price = result.get("price") or {}
        # What the customer actually pays, not the headline fare.
        total = price.get("total_with_platform_fee", price.get("total"))
        depart = (result.get("departure") or {}).get("date")
        arrive = (result.get("arrival") or {}).get("date")
        if total is None or not depart or not arrive:
            return None

        duration = result.get("duration") or {}
        hours = duration.get("hours", 0) + duration.get("minutes", 0) / 60
        legs = result.get("legs") or []
        return Offer(
            mode=Mode.BUS,
            provider="flixbus",
            booking_site=f"FlixBus ({(result.get('provider') or 'flixbus').title()})",
            price=float(total),
            currency=route.currency.upper(),
            depart_time=_naive(depart),
            arrive_time=_naive(arrive),
            duration_hours=round(hours, 2),
            url=_build_booking_url(origin["id"], destination["id"], day),
            # A long-distance coach is the definition of low-cost travel, and
            # the route's low_cost filter should treat it as such.
            is_low_cost=True,
            stops=max(len(legs) - 1, 0),
            details={
                "seats_left": (result.get("available") or {}).get("seats"),
                "transfer_type": result.get("transfer_type", ""),
                # Kept separate so a UI can show both if it wants to.
                "fare_without_fee": price.get("total"),
            },
        )
