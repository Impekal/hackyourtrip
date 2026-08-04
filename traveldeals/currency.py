"""Currency conversion for the "book in a different currency" check.

Some airlines/hotels price identically-specced fares differently depending
on the currency/locale of the booking site, so comparing a EUR fare against
what the same fare would cost paid in USD/GBP/etc. (at the real market rate)
can surface genuine savings. This module supplies the market rate; the
`currency_hint` step that acts on it lives in engine.py.

Uses the Frankfurter API (https://www.frankfurter.app - ECB reference rates,
free, no key required) when network access is available, and falls back to a
small static rate table otherwise so the pipeline never breaks for lack of
network.
"""
from __future__ import annotations

import requests

_FALLBACK_RATES_PER_EUR = {
    "EUR": 1.0, "USD": 1.08, "GBP": 0.85, "CHF": 0.94,
    "PLN": 4.30, "CZK": 25.10, "SEK": 11.30, "NOK": 11.60,
}

_FRANKFURTER_URL = "https://api.frankfurter.app/latest"


def get_rates_per_eur(timeout: float = 3.0) -> dict[str, float]:
    """Return {currency_code: units per 1 EUR}, live if reachable, else the
    static fallback table."""
    try:
        resp = requests.get(_FRANKFURTER_URL, params={"from": "EUR"}, timeout=timeout)
        resp.raise_for_status()
        rates = resp.json().get("rates", {})
        rates["EUR"] = 1.0
        return {**_FALLBACK_RATES_PER_EUR, **rates}
    except requests.RequestException:
        return dict(_FALLBACK_RATES_PER_EUR)


def convert(amount: float, from_currency: str, to_currency: str, rates_per_eur: dict[str, float]) -> float:
    if from_currency == to_currency:
        return amount
    if from_currency not in rates_per_eur or to_currency not in rates_per_eur:
        return amount
    amount_in_eur = amount / rates_per_eur[from_currency]
    return round(amount_in_eur * rates_per_eur[to_currency], 2)
