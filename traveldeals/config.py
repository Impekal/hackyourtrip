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

from traveldeals.models import BaggagePref, Mode, Priority, RailPref, RoutePreference


def _parse_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _parse_route(raw: dict) -> RoutePreference:
    baggage_raw = raw.get("baggage", {}) or {}
    rail_raw = raw.get("rail", {}) or {}
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
        low_cost_airlines_ok=bool(raw.get("low_cost_airlines_ok", True)),
        notes=raw.get("notes", ""),
    )


def load_routes(path: Path) -> list[RoutePreference]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text()) or {}
    return [_parse_route(r) for r in raw.get("routes", [])]
