"""Echte Hotelraten über LiteAPI (Nuitee) - die einzige gefundene freie Quelle.

Neun Recherche-Runden davor sind ohne Ergebnis geblieben (HANDOFF.md): die
Hotellook-/Travelpayouts-Familie ist abgeschaltet, Booking Demand API,
RateHawk und Expedia verlangen einen unterschriebenen Vertrag. LiteAPI
vergibt Schlüssel selbst - und der **kostenlose Sandbox-Schlüssel liefert
echte Raten**, nicht bloß Testdaten. Gemessen in Probe 16 (09.08.2026):
dieselben drei Berliner Hotels über fünf Abfragevarianten (Nachbartag,
3 statt 1 Nacht, 1 statt 2 Erwachsene, 240 statt 30 Tage Vorlauf) ergaben
fünf verschiedene Preise pro Hotel. Testdaten hätten fünfmal dieselbe Zahl
geliefert.

Zwei Eigenheiten dieser Quelle, gemessen in Probe 17, prägen den Code unten:

1. **Ein Zimmer trägt drei Beträge.** `offerRetailRate` ist, was der Reisende
   zahlt; `suggestedSellingPrice` ist der Preis desselben Zimmers auf
   booking.com (LiteAPI nennt die Quelle selbst); `offerInitialPrice` ist der
   Preis vor Rabatt. Der falsche davon wäre ein Preis, den niemand bekommt.

2. **`taxesAndFees` hat ein `included`-Flag, und es ist für die deutsche
   City Tax tatsächlich `false`.** 260,45 EUR ist deshalb *nicht* der Preis
   der Nacht - 280,01 EUR ist es. Genau diese Unterscheidung trennt eine
   ehrliche Summe von einem Lockpreis, und sie ist der Grund, warum
   `_cheapest_offer` nach Gesamtpreis sucht und nicht nach dem genannten
   Betrag.

Was diese Quelle **nicht** weiß: Ausstattung. `facilityIds` sind nackte
Zahlen ([47, 107, 2]) ohne Namenstabelle. Deshalb bleiben WLAN, Parkplatz,
Pool usw. hier `None` - unbekannt, nicht "nein". Die Filterlogik in
engine.py behandelt beides ausdrücklich verschieden.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import requests

from traveldeals.models import Mode, Offer, RoutePreference
from traveldeals.providers.base import Provider, date_candidates

BASE_URL = "https://api.liteapi.travel/v3.0"
TIMEOUT = 30
# Je Anreisetag eine Ratenabfrage; der Sandbox-Schlüssel verträgt 5 pro
# Sekunde, ein Preisalarm liegt weit darunter.
MAX_CHECKINS = 3
MAX_HOTELS = 20
# Der Rest der App rechnet durchgehend mit einer reisenden Person (die
# Flugsuche fragt `adults=1`). Ein Hotelzimmer für zwei zu bepreisen und in
# einer Flug+Hotel-Kombi mit einem Einzelflug zu addieren, ergäbe eine Summe,
# die für niemanden stimmt. Ein Feld für die Personenzahl gibt es (noch)
# nicht - sobald es eins gibt, gehört es hierhin.
ADULTS = 1

# LiteAPI nennt die Verpflegung im Klartext. Alles, was hier nicht steht,
# bleibt None - lieber keine Angabe als eine geratene.
_BOARD_TO_MEAL_PLAN = [
    ("all inclusive", "all_inclusive"),
    ("full board", "full_board"),
    ("half board", "half_board"),
    ("breakfast", "breakfast"),
    ("room only", "none"),
]


def _meal_plan(board_name: str | None) -> str | None:
    text = (board_name or "").lower()
    if not text:
        return None
    for needle, tier in _BOARD_TO_MEAL_PLAN:
        if needle in text:
            return tier
    return None


def _amount(node) -> float | None:
    """Betrag aus `{"amount": x}` oder `[{"amount": x}]`."""
    if isinstance(node, list):
        node = node[0] if node else None
    if not isinstance(node, dict):
        return None
    try:
        return float(node["amount"])
    except (KeyError, TypeError, ValueError):
        return None


def _not_included_taxes(rate: dict) -> float:
    """Summe der Steuern, die im genannten Betrag NICHT stecken."""
    total = 0.0
    for tax in (rate.get("retailRate") or {}).get("taxesAndFees") or []:
        if isinstance(tax, dict) and tax.get("included") is False:
            amount = _amount(tax)
            if amount is not None:
                total += amount
    return total


def _cheapest_offer(entry: dict) -> dict | None:
    """Das günstigste Zimmer eines Hotels - nach Gesamtpreis.

    Nach dem genannten Betrag zu sortieren wäre falsch herum: eine Rate, die
    die City Tax verschweigt, würde damit gegen eine gewinnen, die sie
    enthält.
    """
    best = None
    for room in entry.get("roomTypes") or []:
        price = _amount(room.get("offerRetailRate"))
        if price is None:
            continue
        rate = (room.get("rates") or [{}])[0]
        extra_tax = _not_included_taxes(rate)
        total = round(price + extra_tax, 2)
        if best is not None and total >= best["total"]:
            continue
        compare_at = _amount(room.get("suggestedSellingPrice"))
        best = {
            "total": total,
            "price": price,
            "extra_tax": round(extra_tax, 2),
            "currency": (room.get("offerRetailRate") or {}).get("currency") or "EUR",
            "room_name": rate.get("name"),
            "board_name": rate.get("boardName"),
            # "NRFN" = nicht erstattbar. Alles andere bleibt None statt True:
            # ein falsches "kostenlos stornierbar" kostet echtes Geld.
            "free_cancellation": False
            if (rate.get("cancellationPolicies") or {}).get("refundableTag") == "NRFN"
            else None,
            # Nur behalten, wenn er über unserem Preis liegt - eine
            # "Ersparnis" von null ist keine.
            "compare_at": compare_at if (compare_at or 0) > total else None,
            "compare_source": (room.get("suggestedSellingPrice") or {}).get("source"),
        }
    return best


class LiteApiHotelProvider(Provider):
    """Hotelpreise für den Preisalarm. Ohne LITEAPI_KEY schlicht still."""

    mode = Mode.HOTEL

    def __init__(self, api_key: str | None = None, session=None):
        self.api_key = api_key if api_key is not None else os.environ.get("LITEAPI_KEY", "")
        self.session = session or requests

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, path: str, params: dict) -> dict | None:
        try:
            resp = self.session.get(f"{BASE_URL}{path}", params=params,
                                    headers={"X-API-Key": self.api_key,
                                             "Accept": "application/json"},
                                    timeout=TIMEOUT)
            if resp.status_code != 200:
                return None
            return resp.json()
        except Exception:
            return None

    def _post(self, path: str, body: dict) -> dict | None:
        try:
            resp = self.session.post(f"{BASE_URL}{path}", json=body,
                                     headers={"X-API-Key": self.api_key,
                                              "Accept": "application/json"},
                                     timeout=TIMEOUT)
            if resp.status_code != 200:
                return None
            return resp.json()
        except Exception:
            return None

    def search(self, route: RoutePreference) -> list[Offer]:
        if not self.configured:
            return []
        city, country = _split_destination(route.destination)
        if not country:
            return []

        listing = self._get("/data/hotels", {"countryCode": country,
                                             "cityName": city,
                                             "limit": MAX_HOTELS})
        hotels = (listing or {}).get("data") or []
        if not hotels:
            return []
        by_id = {h["id"]: h for h in hotels if h.get("id")}

        nights = max(route.min_nights or 1, 1)
        offers: list[Offer] = []
        for checkin in date_candidates(route)[:MAX_CHECKINS]:
            checkout = checkin + timedelta(days=nights)
            payload = self._post("/hotels/rates", {
                "hotelIds": list(by_id),
                "occupancies": [{"adults": ADULTS}],
                "currency": route.currency or "EUR",
                "guestNationality": "DE",
                "checkin": checkin.isoformat(),
                "checkout": checkout.isoformat(),
            })
            for entry in (payload or {}).get("data") or []:
                hotel = by_id.get(entry.get("hotelId"))
                best = _cheapest_offer(entry)
                if not hotel or not best or best["total"] <= 0:
                    continue
                depart = datetime.combine(checkin, datetime.min.time()).replace(hour=15)
                arrive = datetime.combine(checkout, datetime.min.time()).replace(hour=11)
                offers.append(Offer(
                    mode=Mode.HOTEL,
                    provider="liteapi",
                    booking_site=hotel.get("name") or "Hotel",
                    price=best["total"],
                    currency=best["currency"],
                    depart_time=depart.isoformat(),
                    arrive_time=arrive.isoformat(),
                    duration_hours=nights * 24,
                    url=_booking_url(hotel, checkin, checkout),
                    stars=hotel.get("stars"),
                    rating=hotel.get("rating"),
                    meal_plan=_meal_plan(best["board_name"]),
                    free_cancellation=best["free_cancellation"],
                    # Unterkunftsart, Entfernung und jede Ausstattung sagt
                    # diese Quelle nicht. Sie bleiben None - siehe
                    # _meets_hotel_constraints.
                    property_type=None,
                ))
        return offers


def _split_destination(destination: str) -> tuple[str, str]:
    """„Berlin, DE" -> ("Berlin", "DE").

    Der Preisalarm liest sein Ziel aus routes.yaml, also aus einer von Hand
    gepflegten Zeile. Ohne Länderkürzel kann LiteAPI nicht suchen, und zu
    raten wäre der falsche Dienst: „Frankfurt" gibt es auch in Kentucky.
    """
    parts = [p.strip() for p in (destination or "").split(",")]
    if len(parts) >= 2 and len(parts[-1]) == 2:
        return parts[0], parts[-1].upper()
    return (parts[0] if parts else ""), ""


def _booking_url(hotel: dict, checkin, checkout) -> str:
    from urllib.parse import urlencode
    name = hotel.get("name") or ""
    city = hotel.get("city") or ""
    return "https://www.booking.com/searchresults.de.html?" + urlencode({
        "ss": f"{name}, {city}" if city else name,
        "checkin": checkin.isoformat(),
        "checkout": checkout.isoformat(),
    })
