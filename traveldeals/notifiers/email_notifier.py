"""Email notifications via plain SMTP (works with Gmail app passwords,
any provider's SMTP relay, etc.). Config via env - see .env.example."""
from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText

from traveldeals.notifiers.base import Notifier


class EmailNotifier(Notifier):
    def __init__(self):
        self.host = os.environ.get("SMTP_HOST")
        self.port = int(os.environ.get("SMTP_PORT", "587"))
        self.user = os.environ.get("SMTP_USER")
        self.password = os.environ.get("SMTP_PASS")
        self.from_addr = os.environ.get("SMTP_FROM", self.user)
        self.to_addr = os.environ.get("SMTP_TO", self.user)

    @property
    def configured(self) -> bool:
        return bool(self.host and self.user and self.password and self.to_addr)

    def send(self, title: str, body: str) -> None:
        if not self.configured:
            print(f"[email] not configured, skipping: {title}")
            return
        msg = MIMEText(body)
        msg["Subject"] = title
        msg["From"] = self.from_addr
        msg["To"] = self.to_addr
        with smtplib.SMTP(self.host, self.port) as server:
            server.starttls()
            server.login(self.user, self.password)
            server.sendmail(self.from_addr, [self.to_addr], msg.as_string())
