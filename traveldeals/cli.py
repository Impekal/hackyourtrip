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
from traveldeals.providers.base import Provider
from traveldeals.providers.mock import (MockBusProvider, MockFlightProvider,
                                         MockHotelProvider, MockTrainProvider)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "config" / "routes.yaml"
DEFAULT_DATA_DIR = REPO_ROOT / "data"
DEFAULT_DASHBOARD_JSON = REPO_ROOT / "docs" / "data" / "deals.json"


def build_providers() -> dict[Mode, Provider]:
    # Flight uses the real Amadeus adapter once AMADEUS_API_KEY/SECRET are
    # set (see providers/amadeus.py); train/bus/hotel are still mock.py
    # until their real adapters (providers/real.py) get implemented.
    amadeus = AmadeusFlightProvider()
    flight_provider = amadeus if amadeus.configured else MockFlightProvider()
    return {
        Mode.FLIGHT: flight_provider,
        Mode.TRAIN: MockTrainProvider(),
        Mode.BUS: MockBusProvider(),
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
