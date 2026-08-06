"""CLI entry point.

    python -m traveldeals.cli check          # run the full pipeline once
    python -m traveldeals.cli list-routes    # show configured routes

This is what the GitHub Actions cron (.github/workflows/check-deals.yml)
calls on a schedule - see README.md for local setup.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from traveldeals.config import load_routes
from traveldeals.engine import DealEngine
from traveldeals.models import Mode, TripOption
from traveldeals.notifiers.base import Notifier
from traveldeals.notifiers.console import ConsoleNotifier
from traveldeals.notifiers.email_notifier import EmailNotifier
from traveldeals.notifiers.telegram import TelegramNotifier
from traveldeals.pricehistory import PriceHistory
from traveldeals.providers.amadeus import AmadeusFlightProvider
from traveldeals.providers.base import CompositeProvider, Provider
from traveldeals.providers.flixbus import FlixbusProvider
from traveldeals.providers.mock import (MockBusProvider, MockFlightProvider,
                                         MockHotelProvider, MockTrainProvider)
from traveldeals.providers.ryanair import RyanairFlightProvider
from traveldeals.providers.transitous import (TransitousBusProvider,
                                               TransitousTrainProvider)
from traveldeals.providers.travelpayouts import TravelpayoutsFlightProvider

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "config" / "routes.yaml"
DEFAULT_DATA_DIR = REPO_ROOT / "data"
DEFAULT_DASHBOARD_JSON = REPO_ROOT / "docs" / "data" / "deals.json"


def _select_flight_provider(allow_mock: bool = True) -> Provider:
    """All available real flight sources at once, merged.

    Ryanair needs no credentials at all and returns live, bookable fares -
    but only for its own routes, so it is a complement, never a replacement.
    Travelpayouts covers many airlines (free self-serve token, see README)
    as a cache of recently seen fares. Amadeus stays supported for anyone
    with an Enterprise account; its free self-service tier was decommissioned
    in July 2026.

    Only if none of them can answer does the mock generator step in - and
    with allow_mock=False not even then, because an empty result is honest
    and an invented price is not.
    """
    real: list[Provider] = [RyanairFlightProvider()]
    travelpayouts = TravelpayoutsFlightProvider()
    if travelpayouts.configured:
        real.append(travelpayouts)
    amadeus = AmadeusFlightProvider()
    if amadeus.configured:
        real.append(amadeus)
    if allow_mock:
        real.append(MockFlightProvider())
    return CompositeProvider(Mode.FLIGHT, real)


def build_providers(real_transit: bool = True) -> dict[Mode, Provider]:
    """Train and bus now come from Transitous - real timetables, no key, and
    deliberately no price (see providers/transitous.py). Hotels stay mocked;
    no free, signup-free source for hotel prices was found.

    Pass real_transit=False to fall back to the mock timetable generators,
    e.g. for an offline demo run.
    """
    return {
        Mode.FLIGHT: _select_flight_provider(allow_mock=not real_transit),
        Mode.TRAIN: TransitousTrainProvider() if real_transit else MockTrainProvider(),
        # Bus is the one ground mode with real prices: FlixBus first,
        # Transitous behind it for the coaches FlixBus doesn't run.
        Mode.BUS: CompositeProvider(Mode.BUS, [FlixbusProvider(), TransitousBusProvider()])
                   if real_transit else MockBusProvider(),
        Mode.HOTEL: MockHotelProvider(),
    }


def build_notifiers() -> list[Notifier]:
    notifiers: list[Notifier] = [ConsoleNotifier()]
    telegram = TelegramNotifier()
    if telegram.configured:
        notifiers.append(telegram)
    email = EmailNotifier()
    if email.configured:
        notifiers.append(email)
    return notifiers


def _option_to_dict(option: TripOption) -> dict:
    return {
        "mode": option.mode.value,
        "total_price": option.total_price,
        # Without this the dashboard would print the 0.0 placeholder as a
        # price; see Offer.price_known.
        "has_unknown_price": option.has_unknown_price,
        "currency": option.currency,
        "total_duration_hours": option.total_duration_hours,
        "is_error_fare": option.is_error_fare,
        "is_price_drop": option.is_price_drop,
        "recommendations": option.recommendations,
        "booking_sites": option.booking_sites,
        "offers": [
            {
                "mode": o.mode.value, "provider": o.provider, "booking_site": o.booking_site,
                "price": o.price, "currency": o.currency, "depart_time": o.depart_time,
                "arrive_time": o.arrive_time, "duration_hours": o.duration_hours, "url": o.url,
                "return_depart_time": o.return_depart_time,
                "price_known": o.price_known, "line_label": o.line_label,
            }
            for o in option.offers
        ],
    }


def run_check(config_path: Path = DEFAULT_CONFIG, data_dir: Path = DEFAULT_DATA_DIR,
              dashboard_path: Path = DEFAULT_DASHBOARD_JSON) -> None:
    routes = load_routes(config_path)
    if not routes:
        print(f"Keine Routen in {config_path} gefunden - siehe config/routes.example.yaml")
        return

    price_history = PriceHistory(data_dir / "pricehistory.json")
    engine = DealEngine(build_providers(), price_history)
    notifiers = build_notifiers()

    dashboard_routes = []
    for route in routes:
        options = engine.search(route)
        dashboard_routes.append({
            "id": route.id, "origin": route.origin, "destination": route.destination,
            "notes": route.notes,
            "options": [_option_to_dict(o) for o in options],
        })
        for option in options:
            if not (option.is_error_fare or option.is_price_drop):
                continue
            title = f"{'🔥 Fehlerpreis' if option.is_error_fare else '📉 Preis gefallen'}: {route.origin} → {route.destination}"
            body = f"{option.mode.value}: {option.total_price} {option.currency}\n" + "\n".join(option.recommendations)
            for notifier in notifiers:
                notifier.send(title, body)

    price_history.save()
    dashboard_path.parent.mkdir(parents=True, exist_ok=True)
    dashboard_path.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "routes": dashboard_routes,
    }, indent=2, ensure_ascii=False))
    print(f"Dashboard-Daten geschrieben nach {dashboard_path}")


def list_routes(config_path: Path = DEFAULT_CONFIG) -> None:
    routes = load_routes(config_path)
    if not routes:
        print(f"Keine Routen in {config_path} gefunden - siehe config/routes.example.yaml")
        return
    for r in routes:
        print(f"- {r.id}: {r.origin} → {r.destination} "
              f"({r.depart_date_from}..{r.depart_date_until}, +/-{r.flex_days_before}/{r.flex_days_after}d), "
              f"Budget={r.budget or '-'} {r.currency}, Priorität={r.priority.value}, Modi={[m.value for m in r.modes]}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="traveldeals")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    sub.add_parser("list-routes")
    args = parser.parse_args()

    if args.command == "check":
        run_check(config_path=args.config)
    elif args.command == "list-routes":
        list_routes(config_path=args.config)


if __name__ == "__main__":
    main()
