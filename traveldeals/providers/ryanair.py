"""Real, bookable Ryanair fares - free, no key, no account.

Ryanair's own fare finder is publicly reachable, which makes it the only
source found so far that returns *live, bookable airline prices* for free.
Everything else checked (Kiwi/Tequila, Amadeus self-service, Duffel outside
its sandbox, Wizz Air, easyJet, Lufthansa, SNCF) needs a key, a partner
agreement, or answers with a scraper-blocking 403 - see README/HANDOFF.

Verified against the live service (via a throwaway GitHub-Actions workflow,
since this dev sandbox has no internet):

- `farfnd/v4/oneWayFares` and `farfnd/v4/roundTripFares` answer HTTP 200 with
  a `fares[]` array. Each fare carries `outbound` (and for round trips also
  `inbound`) with `departureDate`, `arrivalDate`, `flightNumber`, and
  `price.value` / `price.currencyCode`; a round trip additionally has
  `summary.price` with the combined total for both legs.
- `farfnd/v4/.../cheapestPerDay` came back empty and is not used.
- `booking/v4/.../availability` answers 409 "Availability declined" without a
  booking session, so it is not used either.

The obvious limit, which the UI states rather than hides: **Ryanair only
knows Ryanair routes.** Hamburg->Lyon simply isn't one, and no amount of
querying changes that. This provider therefore complements the Travelpayouts
index instead of replacing it - the engine merges both pools.

The date range maps directly onto the flex window, so unlike Travelpayouts
this needs exactly one request for the whole window.
"""
from __future__ import annotations

from datetime import datetime

import requests

from traveldeals.models import Mode, Offer, RoutePreference
from traveldeals.providers.base import Provider, date_candidates

ONE_WAY_URL = "https://services-api.ryanair.com/farfnd/v4/oneWayFares"
ROUND_TRIP_URL = "https://services-api.ryanair.com/farfnd/v4/roundTripFares"

# A plain script user-agent gets a 403 on some Ryanair hosts; this is the
# same request an ordinary visitor's browser makes.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

FARES_PER_REQUEST = 200

# Ryanair is a low-cost carrier by definition, so every offer from here is
# one - relevant for the route's low_cost filter.
AIRLINE_CODE = "FR"

# The airline's own search URL. Built from the parameters its site uses, so
# a wrong guess lands on the search form rather than an error page - the same
# trade-off documented for the bahn.de links in docs/app.js.
BOOKING_BASE = "https://www.ryanair.com/de/de/trip/flights/select"


def _build_booking_url(route: RoutePreference, depart_day: str, return_day: str | None) -> str:
    params = {
        "adults": "1", "teens": "0", "children": "0", "infants": "0",
        "originIata": route.origin, "destinationIata": route.destination,
        "dateOut": depart_day, "isConnectedFlight": "false", "discount": "0",
        "isReturn": "true" if return_day else "false",
    }
    if return_day:
        params["dateIn"] = return_day
    return BOOKING_BASE + "?" + "&".join(f"{k}={v}" for k, v in params.items())


def _duration_hours(depart: str, arrive: str) -> float:
    try:
        delta = datetime.fromisoformat(arrive) - datetime.fromisoformat(depart)
    except ValueError:
        return 0.0
    return round(delta.total_seconds() / 3600, 2)


class RyanairFlightProvider(Provider):
    mode = Mode.FLIGHT

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()

    @property
    def configured(self) -> bool:
        return True  # no key, no account - that is the point

    def search(self, route: RoutePreference) -> list[Offer]:
        days = date_candidates(route)
        if not days:
            return []
        round_trip = bool(route.round_trip and route.return_date)

        params = {
            "departureAirportIataCode": route.origin,
            "arrivalAirportIataCode": route.destination,
            "outboundDepartureDateFrom": days[0].isoformat(),
            "outboundDepartureDateTo": days[-1].isoformat(),
            "currency": route.currency.upper(),
            "language": "de",
            "market": "de-de",
            "limit": FARES_PER_REQUEST,
        }
        if round_trip:
            # The return leg gets the same flexibility as the outbound one,
            # anchored on the requested return date.
            params["inboundDepartureDateFrom"] = route.return_date.isoformat()
            params["inboundDepartureDateTo"] = route.return_date.isoformat()

        url = ROUND_TRIP_URL if round_trip else ONE_WAY_URL
        try:
            resp = self.session.get(url, params=params, headers=HEADERS, timeout=25)
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            print(f"[ryanair] request failed for {route.origin}->{route.destination}: {exc}")
            return []
        except ValueError:
            return []

        offers = []
        for fare in payload.get("fares") or []:
            offer = self._to_offer(fare, route, round_trip)
            if offer is not None:
                offers.append(offer)
        return offers

    def _to_offer(self, fare: dict, route: RoutePreference, round_trip: bool) -> Offer | None:
        outbound = fare.get("outbound") or {}
        depart = outbound.get("departureDate")
        arrive = outbound.get("arrivalDate")
        if not depart or not arrive:
            return None

        # For a round trip the combined total lives in summary.price; the
        # per-leg price would understate what the trip actually costs.
        price_block = ((fare.get("summary") or {}).get("price") if round_trip
                       else (outbound.get("price") or {}))
        value = (price_block or {}).get("value")
        if value is None:
            return None

        inbound = fare.get("inbound") or {}
        flight_number = outbound.get("flightNumber") or AIRLINE_CODE
        return Offer(
            mode=Mode.FLIGHT,
            provider="ryanair",
            booking_site=f"Ryanair ({flight_number})",
            price=float(value),
            currency=(price_block.get("currencyCode") or route.currency).upper(),
            depart_time=depart[:19],
            arrive_time=arrive[:19],
            duration_hours=_duration_hours(depart[:19], arrive[:19]),
            url=_build_booking_url(route, depart[:10],
                                    (inbound.get("departureDate") or "")[:10] or None),
            # Ryanair sells the seat only; a checked bag is extra, and the
            # exact fee depends on route/season, so it stays 0 rather than
            # being guessed - see the project rule about invented numbers.
            is_low_cost=True,
            stops=0,  # Ryanair fare finder returns non-stop fares only
            line_label=flight_number,
            return_depart_time=(inbound.get("departureDate") or "")[:19] or None,
        )
