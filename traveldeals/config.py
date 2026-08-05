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


def _parse_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


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
        priority=Priority(raw.get("priority", "best_value")),
        modes=[Mode(m) for m in raw.get("modes", ["flight"])],
        baggage=BaggagePref(
            carry_on_only=bool(baggage_raw.get("carry_on_only", False)),
            checked_bags=int(baggage_raw.get("checked_bags", 0)),
            checked_bag_kg=int(baggage_raw.get("checked_bag_kg", 23)),
        ),
        rail=RailPref(
            bahncard=rail_raw.get("bahncard"),
            deutschlandticket=bool(rail_raw.get("deutschlandticket", False)),
        ),
        hotel=HotelPref(
            min_stars=hotel_raw.get("min_stars"),
            min_rating=hotel_raw.get("min_rating"),
            max_distance_km=hotel_raw.get("max_distance_km"),
            require_wifi=bool(hotel_raw.get("require_wifi", False)),
            require_breakfast=bool(hotel_raw.get("require_breakfast", False)),
            require_free_cancellation=bool(hotel_raw.get("require_free_cancellation", False)),
            require_parking=bool(hotel_raw.get("require_parking", False)),
            require_air_conditioning=bool(hotel_raw.get("require_air_conditioning", False)),
            require_pets_allowed=bool(hotel_raw.get("require_pets_allowed", False)),
            require_pool_or_fitness=bool(hotel_raw.get("require_pool_or_fitness", False)),
        ),
        transport=TransportPref(
            direct_only=bool(transport_raw.get("direct_only", False)),
            require_wifi_onboard=bool(transport_raw.get("require_wifi_onboard", False)),
            require_power_outlets=bool(transport_raw.get("require_power_outlets", False)),
            min_punctuality_pct=transport_raw.get("min_punctuality_pct"),
            preferred_depart_time=transport_raw.get("preferred_depart_time"),
            depart_time_flex_minutes=int(transport_raw.get("depart_time_flex_minutes", 0)),
        ),
        low_cost_airlines_ok=bool(raw.get("low_cost_airlines_ok", True)),
        round_trip=bool(raw.get("round_trip", False)),
        return_date=_parse_date(raw["return_date"]) if raw.get("return_date") else None,
        notes=raw.get("notes", ""),
    )


def load_routes(path: Path) -> list[RoutePreference]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text()) or {}
    return [_parse_route(r) for r in raw.get("routes", [])]
