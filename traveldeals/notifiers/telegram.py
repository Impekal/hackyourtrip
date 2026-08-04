"""Telegram push notifications.

Setup: message @BotFather on Telegram, /newbot, copy the token into
TELEGRAM_BOT_TOKEN. Then message your new bot once and call
https://api.telegram.org/bot<token>/getUpdates to read your chat id into
TELEGRAM_CHAT_ID. Both are read from the environment - see .env.example.
"""
from __future__ import annotations

import os

import requests

from traveldeals.notifiers.base import Notifier

_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier(Notifier):
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, title: str, body: str) -> None:
        if not self.configured:
            print(f"[telegram] not configured, skipping: {title}")
            return
        text = f"*{title}*\n{body}"
        resp = requests.post(
            _API_URL.format(token=self.token),
            json={"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        resp.raise_for_status()
