"""Loads tracked routes from a YAML file into RoutePreference objects.

v1 has no user accounts/database - you track routes by editing
config/routes.yaml directly (copy config/routes.example.yaml to start).
That's the whole "settings UI" for now; see README.md roadmap for the plan
to grow this into a real multi-user web form (e.g. via Supabase, mirroring
the sister mysportpilot project) once real provider APIs are wired up.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from traveldeals.models import (BaggagePref, HotelPref, Mode, Priority,
                                 RailPref, RoutePreference, TransportPref)

# Every HotelPref boolean amenity flag - field name doubles as its YAML key,
# so a new amenity only needs adding here (+ to the dataclass) rather than
# another explicit bool(...) line.
_HOTEL_REQUIRE_FIELDS = [
    "require_wifi", "require_free_cancellation", "require_parking",
    "require_air_conditioning", "require_pets_allowed", "require_pool",
    "require_gym", "require_spa", "require_restaurant", "require_bar",
    "require_room_service", "require_24h_front_desk", "require_business_facilities",
    "require_laundry_service", "require_elevator", "require_balcony_or_terrace",
    "require_kitchen", "require_beachfront", "require_disabled_access",
    "require_ev_charging", "require_bicycle_rental", "require_babysitting",
    "require_sauna", "require_hot_tub", "require_non_smoking",
    "require_family_rooms", "require_airport_shuttle",
]


def _parse_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _optional_float(value) -> float | None:
    """None (explicit `null` in YAML, or an "egal" checkbox client-side)
    means no baggage-weight preference stated - distinct from 0."""
    return None if value is None else float(value)


def _parse_return_date(raw: dict, depart_from: date) -> date | None:
    """A return before the outbound is not a trip.

    The web form prevents it with the date field's `min`, but routes.yaml is
    hand-edited and has no such guard. Dropping the date (and saying so) is
    better than silently searching a reversed trip - and better than
    inventing a corrected date the user never wrote.
    """
    if not raw.get("return_date"):
        return None
    return_date = _parse_date(raw["return_date"])
    if return_date < depart_from:
        print(f"[config] Route {raw.get('id', '?')!r}: return_date {return_date} liegt vor "
              f"depart_date_from {depart_from} - wird ignoriert, Suche läuft als reine Hinreise.")
        return None
    return return_date


def _parse_route(raw: dict) -> RoutePreference:
    baggage_raw = raw.get("baggage", {}) or {}
    rail_raw = raw.get("rail", {}) or {}
    hotel_raw = raw.get("hotel", {}) or {}
    transport_raw = raw.get("transport", {}) or {}
    return RoutePreference(
        id=raw["id"],
        origin=raw["origin"],
        destination=raw["destination"],
        depart_date_from=_parse_date(raw["depart_date_from"]),
        depart_date_until=_parse_date(raw["depart_date_until"]),
        flex_days_before=int(raw.get("flex_days_before", 0)),
        flex_days_after=int(raw.get("flex_days_after", 0)),
        min_nights=int(raw.get("min_nights", 0)),
        max_nights=int(raw.get("max_nights", 0)),
        budget=raw.get("budget"),
        currency=raw.get("currency", "EUR"),
        max_duration_hours=raw.get("max_duration_hours"),
        max_duration_return_hours=raw.get("max_duration_return_hours"),
        priority=Priority(raw.get("priority", "best_value")),
        modes=[Mode(m) for m in raw.get("modes", ["flight"])],
        baggage=BaggagePref(
            checked_bags=int(baggage_raw.get("checked_bags", 0)),
            checked_bag_kg=_optional_float(baggage_raw.get("checked_bag_kg", 23)),
            carry_on_count=int(baggage_raw.get("carry_on_count", 1)),
            carry_on_max_kg=_optional_float(baggage_raw.get("carry_on_max_kg", 8.0)),
        ),
        rail=RailPref(
            bahncard=rail_raw.get("bahncard"),
            deutschlandticket=bool(rail_raw.get("deutschlandticket", False)),
        ),
        hotel=HotelPref(
            min_stars=hotel_raw.get("min_stars"),
            min_rating=hotel_raw.get("min_rating"),
            max_distance_km=hotel_raw.get("max_distance_km"),
            property_types=list(hotel_raw.get("property_types", []) or []),
            min_meal_plan=hotel_raw.get("min_meal_plan"),
            **{f: bool(hotel_raw.get(f, False)) for f in _HOTEL_REQUIRE_FIELDS},
        ),
        transport=TransportPref(
            direct_only=bool(transport_raw.get("direct_only", False)),
            require_wifi_onboard=bool(transport_raw.get("require_wifi_onboard", False)),
            require_power_outlets=bool(transport_raw.get("require_power_outlets", False)),
            min_punctuality_pct=transport_raw.get("min_punctuality_pct"),
            preferred_depart_time=transport_raw.get("preferred_depart_time"),
            depart_time_flex_minutes=int(transport_raw.get("depart_time_flex_minutes", 0)),
        ),
        # Backwards compatible: an old low_cost_airlines_ok: false still
        # means "exclude", so existing routes.yaml files keep working.
        low_cost=raw.get("low_cost") or ("any" if raw.get("low_cost_airlines_ok", True) else "exclude"),
        round_trip=bool(raw.get("round_trip", False)),
        deals_only=bool(raw.get("deals_only", False)),
        # Backwards compatible: the old single nearby_km applied to both
        # ends, so an existing routes.yaml keeps behaving the same.
        nearby_origin_km=int(raw.get("nearby_origin_km", raw.get("nearby_km", 0)) or 0),
        nearby_destination_km=int(raw.get("nearby_destination_km", raw.get("nearby_km", 0)) or 0),
        return_date=_parse_return_date(raw, _parse_date(raw["depart_date_from"])),
        notes=raw.get("notes", ""),
    )


def load_routes(path: Path) -> list[RoutePreference]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text()) or {}
    return [_parse_route(r) for r in raw.get("routes", [])]
