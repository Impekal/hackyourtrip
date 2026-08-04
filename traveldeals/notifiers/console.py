from __future__ import annotations

from traveldeals.notifiers.base import Notifier


class ConsoleNotifier(Notifier):
    """Always-available fallback so `check` has visible output even with no
    Telegram/email credentials configured (e.g. first local test run)."""

    def send(self, title: str, body: str) -> None:
        print(f"\n=== {title} ===\n{body}\n")
