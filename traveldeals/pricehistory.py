"""JSON-file-backed price history, used to tell a genuine deal/error fare
from an ordinary price. A single number ("it costs 80 EUR") means nothing on
its own - it only becomes a "deal" relative to what this route has actually
cost before.
"""
from __future__ import annotations

import json
import statistics
from datetime import date, datetime
from pathlib import Path


class PriceHistory:
    def __init__(self, path: Path):
        self.path = path
        self._data: dict = {}
        if self.path.exists():
            self._data = json.loads(self.path.read_text())

    def _series(self, route_id: str, mode: str) -> list[dict]:
        return self._data.setdefault(route_id, {}).setdefault(mode, [])

    def record(self, route_id: str, mode: str, price: float, currency: str, as_of: date | None = None) -> None:
        as_of = as_of or date.today()
        series = self._series(route_id, mode)
        series.append({"date": as_of.isoformat(), "price": price, "currency": currency})
        # keep at most one entry per day per route/mode to bound file growth
        series[:] = list({e["date"]: e for e in series}.values())
        series.sort(key=lambda e: e["date"])

    def stats(self, route_id: str, mode: str) -> dict | None:
        series = self._data.get(route_id, {}).get(mode, [])
        if not series:
            return None
        prices = [e["price"] for e in series]
        return {
            "count": len(prices),
            "min": min(prices),
            "max": max(prices),
            "median": statistics.median(prices),
        }

    def is_notable_low(self, route_id: str, mode: str, price: float, drop_threshold: float = 0.85,
                        error_fare_threshold: float = 0.5) -> tuple[bool, bool]:
        """Return (is_price_drop, is_error_fare) for `price` vs history.
        Needs at least 3 prior observations to judge - a single sample isn't
        a baseline."""
        stats = self.stats(route_id, mode)
        if not stats or stats["count"] < 3:
            return False, False
        is_drop = price <= stats["median"] * drop_threshold
        is_error = price <= stats["min"] * error_fare_threshold
        return is_drop, is_error

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))
