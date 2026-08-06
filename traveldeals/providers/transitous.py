"""Real train/bus connections from Transitous (MOTIS) - deliberately priced-less.

Transitous (https://transitous.org) is a community-run, free public-transport
routing service built on MOTIS and fed by hundreds of official GTFS feeds. Its
API needs **no key and no registration**, which is why it is here: it was the
only source that survived the search for a free, signup-free replacement for
the invented train/bus data (DB wrappers answered 503, the FlixBus wrapper
does not exist, OpenTripMap wants a key - see README/HANDOFF).

**It returns timetables, not fares.** The `plan` response carries no fare
information at all (`debugOutput.fares` was 0 on every probe). So every Offer
this module produces sets `price_known=False` and leaves `price` at 0.0. That
is the entire point of the module: a real ICE at a real time on a real track,
with the price honestly marked unknown, is worth more than a plausible-looking
number nobody can book. Making one up is what once put a 42 EUR train in front
of a user that the DB app had never heard of.

Two endpoints, both verified against the live service:

- `/api/v1/geocode?text=...` - resolves "Berlin Hbf" to a stop id. Results mix
  stations (`type: "STOP"`) with POIs (`type: "PLACE"`, e.g. the hotel next to
  the station), so only STOPs are considered; the first PLACE hit for
  "München Hbf" was a sauna, which is a good illustration of why.
- `/api/v1/plan?fromPlace=&toPlace=&time=&numItineraries=&transitModes=` -
  returns itineraries with legs, each carrying line name, platform, and both
  scheduled and real-time departure/arrival.

Times come back in UTC ("2026-09-15T08:37:00Z") while the rest of this
codebase uses naive local time, so they are converted into the origin stop's
own timezone (`tz` on the geocode hit / leg endpoint) before being stored.

Request budget: MOTIS answers "the next N connections after `time`", so one
request per day would only ever describe the early morning. Instead each day
is probed at a few anchor times (see DEPART_ANCHORS) and the results merged
and de-duplicated. Days are capped by MAX_DAYS_QUERIED - this is a free
community service, and a wide flex window should not turn into a hundred
requests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from traveldeals.models import Mode, Offer, RoutePreference
from traveldeals.providers.base import Provider, date_candidates

BASE_URL = "https://api.transitous.org/api"

# Local times of day each candidate day is probed at. MOTIS returns the next
# `numItineraries` departures after the given time, so three anchors spread
# across the day cover morning/midday/evening instead of only the first
# trains after midnight.
DEPART_ANCHORS = ("06:00", "12:00", "18:00")
ITINERARIES_PER_REQUEST = 5
MAX_DAYS_QUERIED = 4

# MOTIS leg modes that count as the mode we're searching for. A leg outside
# these (WALK, SUBWAY, TRAM, ...) is fine as a connecting leg, but an
# itinerary whose *longest* transit leg isn't one of these isn't a train
# journey (or a coach journey) in the sense the user asked for.
TRANSIT_MODES = {
    Mode.TRAIN: ("HIGHSPEED_RAIL", "LONG_DISTANCE", "NIGHT_RAIL", "REGIONAL_FAST_RAIL", "REGIONAL_RAIL", "RAIL"),
    Mode.BUS: ("COACH", "BUS"),
}

# What to tell the API we're willing to travel on. Kept wider than
# TRANSIT_MODES on purpose: reaching the long-distance station usually needs
# a local leg, and refusing those would drop otherwise valid connections.
REQUEST_MODES = {
    Mode.TRAIN: "HIGHSPEED_RAIL,LONG_DISTANCE,NIGHT_RAIL,REGIONAL_FAST_RAIL,REGIONAL_RAIL,SUBURBAN,SUBWAY,TRAM,WALK",
    Mode.BUS: "COACH,BUS,SUBURBAN,SUBWAY,TRAM,WALK",
}

# Transitous asks API users to identify themselves so they can get in touch
# about traffic rather than just blocking it.
USER_AGENT = "HackYourTrip/1.0 (+https://github.com/kalivolut/hackyourtrip)"


def _to_local_naive(utc_iso: str, tz_name: str) -> str:
    """"2026-09-15T08:37:00Z" + "Europe/Berlin" -> "2026-09-15T10:37:00".

    Everything else in this codebase (mock providers, Travelpayouts, the
    engine's depart-time window) speaks naive local time, so timetable data
    has to be converted rather than dragged around with a UTC offset.
    """
    moment = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    try:
        local = moment.astimezone(ZoneInfo(tz_name))
    except (ZoneInfoNotFoundError, ValueError):
        local = moment.astimezone(timezone.utc)
    return local.replace(tzinfo=None).isoformat(timespec="seconds")


def _local_anchor_to_utc(day, hhmm: str, tz_name: str) -> str:
    """The `time` query parameter wants UTC; the anchors are local times."""
    hour, minute = (int(part) for part in hhmm.split(":"))
    naive = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)
    try:
        aware = naive.replace(tzinfo=ZoneInfo(tz_name))
    except (ZoneInfoNotFoundError, ValueError):
        aware = naive.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _leg_label(leg: dict) -> str:
    """"ICE 1007" / "TGV 9575" / "FlixBus 076" - whatever the feed calls the
    vehicle, preferring the display name the service itself composed."""
    for key in ("displayName", "tripShortName", "routeShortName", "routeLongName"):
        value = (leg.get(key) or "").strip()
        if value:
            return value
    return (leg.get("mode") or "").replace("_", " ").title()


class TransitousProvider(Provider):
    """Shared implementation; instantiate the mode-specific subclasses below."""

    #: Mode this instance answers for - set by the subclasses.
    mode: Mode

    def __init__(self, session: requests.Session | None = None, base_url: str = BASE_URL):
        self.session = session or requests.Session()
        self.base_url = base_url.rstrip("/")

    @property
    def configured(self) -> bool:
        return True  # no key, no account - that is the whole appeal

    # -- HTTP -----------------------------------------------------------------

    def _get(self, path: str, params: dict):
        resp = self.session.get(
            f"{self.base_url}{path}", params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=25,
        )
        resp.raise_for_status()
        return resp.json()

    def _resolve_stop(self, text: str) -> dict | None:
        """Best matching *station* for a free-text place, or None.

        Only `type == "STOP"` hits qualify: the geocoder happily returns
        hotels, saunas and city nodes for "München Hbf" too, and routing from
        a sauna is not what the user meant.
        """
        try:
            hits = self._get("/v1/geocode", {"text": text, "language": "de"})
        except requests.RequestException as exc:
            print(f"[transitous] geocode failed for {text!r}: {exc}")
            return None
        stops = [h for h in hits or [] if h.get("type") == "STOP" and h.get("id")]
        if not stops:
            return None
        needle = text.strip().lower()
        exact = [h for h in stops if (h.get("name") or "").strip().lower() == needle]
        return (exact or stops)[0]

    # -- search ---------------------------------------------------------------

    def search(self, route: RoutePreference) -> list[Offer]:
        origin = self._resolve_stop(route.origin)
        destination = self._resolve_stop(route.destination)
        if not origin or not destination:
            return []
        tz_name = origin.get("tz") or "UTC"

        offers: list[Offer] = []
        seen: set[tuple] = set()
        for day in date_candidates(route)[:MAX_DAYS_QUERIED]:
            for anchor in DEPART_ANCHORS:
                try:
                    payload = self._get("/v1/plan", {
                        "fromPlace": origin["id"],
                        "toPlace": destination["id"],
                        "time": _local_anchor_to_utc(day, anchor, tz_name),
                        "numItineraries": ITINERARIES_PER_REQUEST,
                        "transitModes": REQUEST_MODES[self.mode],
                    })
                except requests.RequestException as exc:
                    print(f"[transitous] plan failed for {route.origin}->{route.destination} on {day}: {exc}")
                    continue
                for itinerary in payload.get("itineraries", []):
                    offer = self._to_offer(itinerary, route, tz_name)
                    if offer is None:
                        continue
                    # The anchors overlap by design (an 18:00 request can
                    # return the same train a 12:00 one already did), and a
                    # departure outside the requested days is not wanted at
                    # all - MOTIS will happily roll over past midnight.
                    if offer.depart_time[:10] != day.isoformat():
                        continue
                    key = (offer.depart_time, offer.line_label)
                    if key in seen:
                        continue
                    seen.add(key)
                    offers.append(offer)
        return offers

    def _to_offer(self, itinerary: dict, route: RoutePreference, tz_name: str) -> Offer | None:
        legs = itinerary.get("legs") or []
        wanted = TRANSIT_MODES[self.mode]
        transit_legs = [leg for leg in legs if leg.get("mode") in wanted]
        if not transit_legs:
            # Pure walking/local-transport itinerary - real, but not the
            # train or coach the user is shopping for.
            return None

        start = itinerary.get("startTime")
        end = itinerary.get("endTime")
        if not start or not end:
            return None
        duration_seconds = itinerary.get("duration") or 0

        labels = [_leg_label(leg) for leg in transit_legs]
        agencies = []
        for leg in transit_legs:
            agency = (leg.get("agencyName") or "").strip()
            if agency and agency not in agencies:
                agencies.append(agency)

        first, last = legs[0], legs[-1]
        return Offer(
            mode=self.mode,
            provider="transitous",
            # The operator is a fact from the feed; it is not a booking site,
            # and nothing here claims a bookable price, so this is safe to
            # show verbatim.
            booking_site=" / ".join(agencies) if agencies else "Transitous",
            price=0.0,
            price_known=False,
            currency=route.currency,
            depart_time=_to_local_naive(start, tz_name),
            arrive_time=_to_local_naive(end, tz_name),
            duration_hours=round(duration_seconds / 3600, 2),
            # No booking URL exists for a MOTIS itinerary; the UI offers the
            # operators' own search pages instead of pretending otherwise.
            url="",
            line_label=" → ".join(labels),
            stops=int(itinerary.get("transfers", 0) or 0),
            details={
                "from_stop": (first.get("from") or {}).get("name", route.origin),
                "to_stop": (last.get("to") or {}).get("name", route.destination),
                "track": (first.get("from") or {}).get("track") or "",
                "realtime": bool(transit_legs[0].get("realTime")),
            },
        )


class TransitousTrainProvider(TransitousProvider):
    mode = Mode.TRAIN


class TransitousBusProvider(TransitousProvider):
    mode = Mode.BUS


def nearby_stations(resolver, name: str, radius_km: float, limit: int = 2) -> list[tuple[str, int]]:
    """Stations within `radius_km` of `name`, nearest first.

    Unlike airports there is no static table of station coordinates here, and
    inventing one would make the detour shown to the user wrong by however
    far a city's station sits from its airport. So the airport table is used
    only as a grid of major cities to *propose* candidates; each candidate is
    resolved through Transitous, which returns the real stop with real
    coordinates, and the distance is measured from those.

    `resolver` is anything with a `_resolve_stop(name)` - normally a
    TransitousProvider, injectable for tests.
    """
    from traveldeals.providers.geo import AIRPORT_COORDS, _haversine_km

    origin = resolver._resolve_stop(name)
    if not origin or origin.get("lat") is None or radius_km <= 0:
        return []

    from traveldeals.providers.geo import AIRPORT_COORDS as grid
    candidates = []
    for code, coords in grid.items():
        city = AIRPORT_CITY_NAMES.get(code)
        if not city:
            continue
        # Generous pre-filter: a station can sit tens of km from its city's
        # airport, so cut precisely later on the real coordinates.
        rough = _haversine_km(origin["lat"], origin["lon"], *coords)
        if rough <= radius_km + 60:
            candidates.append((city, rough))
    candidates.sort(key=lambda pair: pair[1])

    found: list[tuple[str, int]] = []
    seen = {origin.get("name")}
    for city, _rough in candidates[:8]:
        stop = resolver._resolve_stop(city)
        if not stop or stop.get("lat") is None or stop.get("name") in seen:
            continue
        km = round(_haversine_km(origin["lat"], origin["lon"], stop["lat"], stop["lon"]))
        if km == 0 or km > radius_km:
            continue
        seen.add(stop["name"])
        found.append((stop["name"], km))
        if len(found) >= limit:
            break
    return found


# IATA -> city name, so the airport grid above can be turned into place names
# Transitous understands. Mirrored in docs/app.js (AIRPORT_CITY_NAMES).
AIRPORT_CITY_NAMES = {
    "BER": "Berlin", "MUC": "München", "FRA": "Frankfurt", "DUS": "Düsseldorf",
    "HAM": "Hamburg", "STR": "Stuttgart", "CGN": "Köln", "HAJ": "Hannover",
    "NUE": "Nürnberg", "LEJ": "Leipzig", "DTM": "Dortmund", "BRE": "Bremen",
    "VIE": "Wien", "ZRH": "Zürich", "GVA": "Genf", "SZG": "Salzburg",
    "INN": "Innsbruck", "BSL": "Basel", "CDG": "Paris", "ORY": "Paris",
    "NCE": "Nizza", "LYS": "Lyon", "MRS": "Marseille", "TLS": "Toulouse",
    "BOD": "Bordeaux", "NTE": "Nantes", "AMS": "Amsterdam", "BRU": "Brüssel",
    "MAD": "Madrid", "BCN": "Barcelona", "VLC": "Valencia", "FCO": "Rom",
    "MXP": "Mailand", "LIN": "Mailand", "VCE": "Venedig", "NAP": "Neapel",
    "LIS": "Lissabon", "OPO": "Porto", "CPH": "Kopenhagen", "WAW": "Warschau",
    "PRG": "Prag", "BUD": "Budapest", "LHR": "London", "MAN": "Manchester",
}
