"""Mock providers.

Generate plausible-looking offers without calling any external API, so the
whole pipeline (engine, ranking, notifiers, dashboard) can be built, tested,
and demoed before real API keys/contracts exist. Every mock is deterministic
for a given route id + a "day bucket" (today's date), so re-running `check`
within the same day doesn't create fake price movement, but running it again
tomorrow does - which is what lets the price-history/drop-detection logic be
exercised realistically over time.

Swap-out plan: each of these becomes a real adapter (Amadeus/Kiwi for
flights, DB/HAFAS for trains, FlixBus for bus, Booking/Trivago for hotels)
behind the same Provider interface - see providers/base.py.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from traveldeals.models import Mode, Offer, RoutePreference
from traveldeals.providers.base import Provider, date_candidates as _date_candidates


def _seed_for(route: RoutePreference, mode: Mode, as_of: date) -> int:
    return hash((route.id, mode.value, as_of.isoformat())) & 0xFFFFFFFF


def _transport_comfort_fields(rnd: random.Random, mode: Mode, stops_weights: list[float]) -> dict:
    """Shared random comfort-field generation for flight/train/bus offers."""
    lo, hi = {Mode.FLIGHT: (66.0, 96.0), Mode.TRAIN: (85.0, 120.0), Mode.BUS: (70.0, 100.0)}[mode]
    return {
        "stops": rnd.choices([0, 1, 2], weights=stops_weights, k=1)[0],
        "wifi_onboard": rnd.random() < 0.6,
        "power_outlets": rnd.random() < 0.55,
        "legroom_cm": round(rnd.uniform(lo, hi), 1),
        "punctuality_pct": round(rnd.uniform(70, 99), 1),
    }


class MockFlightProvider(Provider):
    mode = Mode.FLIGHT
    _BOOKING_SITES = ["Skyscanner", "Google Flights", "Kiwi.com", "Airline direct"]
    _DEPART_HOURS = [6, 9, 12, 15, 18, 21]

    def __init__(self, as_of: date | None = None):
        self.as_of = as_of or date.today()

    def search(self, route: RoutePreference) -> list[Offer]:
        rnd = random.Random(_seed_for(route, self.mode, self.as_of))
        offers: list[Offer] = []
        base_price = rnd.uniform(60, 320)
        for day in _date_candidates(route):
            for hour in rnd.sample(self._DEPART_HOURS, k=min(3, len(self._DEPART_HOURS))):
                # Earlier-morning and evening peak flights cost a premium;
                # this asymmetry is what powers the "leave 1h later, save X"
                # recommendation in engine.py.
                peak_factor = 1.35 if hour in (6, 18) else 1.0
                price = round(base_price * peak_factor * rnd.uniform(0.85, 1.25), 2)
                duration = round(rnd.uniform(1.5, 4.5), 1)
                is_low_cost = rnd.random() < 0.5
                checked_bag_fee = round(rnd.uniform(25, 55), 2) if is_low_cost else 0.0
                depart_dt = datetime(day.year, day.month, day.day, hour, rnd.choice([0, 15, 30, 45]))
                arrive_dt = depart_dt + timedelta(hours=duration)
                offers.append(Offer(
                    mode=self.mode,
                    provider="mock-flight",
                    booking_site=rnd.choice(self._BOOKING_SITES),
                    price=price,
                    currency=route.currency,
                    depart_time=depart_dt.isoformat(),
                    arrive_time=arrive_dt.isoformat(),
                    duration_hours=duration,
                    url="https://example.invalid/flight",
                    checked_bag_fee=checked_bag_fee,
                    is_low_cost=is_low_cost,
                    **_transport_comfort_fields(rnd, self.mode, [0.55, 0.35, 0.10]),
                ))
        # A rare, deliberately-planted "error fare" so the anomaly-detection
        # path (engine.py + pricehistory.py) has something real to catch in
        # a demo, mirroring the "airline mispricing" scenario from the brief.
        if rnd.random() < 0.08:
            day = rnd.choice(_date_candidates(route))
            depart_dt = datetime(day.year, day.month, day.day, 10, 0)
            offers.append(Offer(
                mode=self.mode,
                provider="mock-flight",
                booking_site="Airline direct",
                price=round(base_price * 0.12, 2),
                currency=route.currency,
                depart_time=depart_dt.isoformat(),
                arrive_time=(depart_dt + timedelta(hours=2)).isoformat(),
                duration_hours=2.0,
                url="https://example.invalid/flight-error-fare",
                checked_bag_fee=35.0,
                is_low_cost=True,
            ))
        return offers


class MockTrainProvider(Provider):
    mode = Mode.TRAIN
    _BOOKING_SITES = ["DB Navigator", "Trainline", "Omio"]
    _BAHNCARD_DISCOUNT = {"25": 0.25, "50": 0.50, "100": 1.0, None: 0.0}

    def __init__(self, as_of: date | None = None):
        self.as_of = as_of or date.today()

    def search(self, route: RoutePreference) -> list[Offer]:
        rnd = random.Random(_seed_for(route, self.mode, self.as_of))
        offers: list[Offer] = []
        base_price = rnd.uniform(20, 140)
        discount = self._BAHNCARD_DISCOUNT.get(route.rail.bahncard, 0.0)
        for day in _date_candidates(route):
            for hour in rnd.sample(range(5, 22), k=3):
                price = round(base_price * rnd.uniform(0.8, 1.3) * (1 - discount), 2)
                duration = round(rnd.uniform(2.0, 7.0), 1)
                depart_dt = datetime(day.year, day.month, day.day, hour, rnd.choice([0, 15, 30, 45]))
                arrive_dt = depart_dt + timedelta(hours=duration)
                offers.append(Offer(
                    mode=self.mode,
                    provider="mock-train",
                    booking_site=rnd.choice(self._BOOKING_SITES),
                    price=0.0 if route.rail.bahncard == "100" else price,
                    currency=route.currency,
                    depart_time=depart_dt.isoformat(),
                    arrive_time=arrive_dt.isoformat(),
                    duration_hours=duration,
                    url="https://example.invalid/train",
                    details={"bahncard_applied": route.rail.bahncard,
                             "deutschlandticket_ok": route.rail.deutschlandticket and duration <= 1.0},
                    **_transport_comfort_fields(rnd, self.mode, [0.75, 0.20, 0.05]),
                ))
        return offers


class MockBusProvider(Provider):
    mode = Mode.BUS
    _BOOKING_SITES = ["FlixBus", "Omio"]

    def __init__(self, as_of: date | None = None):
        self.as_of = as_of or date.today()

    def search(self, route: RoutePreference) -> list[Offer]:
        rnd = random.Random(_seed_for(route, self.mode, self.as_of))
        offers: list[Offer] = []
        base_price = rnd.uniform(9, 50)
        for day in _date_candidates(route):
            for hour in rnd.sample(range(0, 24), k=3):
                price = round(base_price * rnd.uniform(0.8, 1.2), 2)
                duration = round(rnd.uniform(3.0, 11.0), 1)
                depart_dt = datetime(day.year, day.month, day.day, hour, rnd.choice([0, 30]))
                arrive_dt = depart_dt + timedelta(hours=duration)
                offers.append(Offer(
                    mode=self.mode,
                    provider="mock-bus",
                    booking_site=rnd.choice(self._BOOKING_SITES),
                    price=price,
                    currency=route.currency,
                    depart_time=depart_dt.isoformat(),
                    arrive_time=arrive_dt.isoformat(),
                    duration_hours=duration,
                    url="https://example.invalid/bus",
                    **_transport_comfort_fields(rnd, self.mode, [0.65, 0.30, 0.05]),
                ))
        return offers


class MockHotelProvider(Provider):
    mode = Mode.HOTEL
    _BOOKING_SITES = ["Booking.com", "Trivago", "Hotels.com", "Airbnb"]

    def __init__(self, as_of: date | None = None):
        self.as_of = as_of or date.today()

    def search(self, route: RoutePreference) -> list[Offer]:
        rnd = random.Random(_seed_for(route, self.mode, self.as_of))
        nights = max(route.min_nights, 1)
        offers: list[Offer] = []
        base_per_night = rnd.uniform(45, 220)
        for checkin in _date_candidates(route)[:5]:
            checkout = checkin + timedelta(days=nights)
            for _ in range(3):
                per_night = round(base_per_night * rnd.uniform(0.85, 1.3), 2)
                total = round(per_night * nights, 2)
                offers.append(Offer(
                    mode=self.mode,
                    provider="mock-hotel",
                    booking_site=rnd.choice(self._BOOKING_SITES),
                    price=total,
                    currency=route.currency,
                    depart_time=checkin.isoformat(),
                    arrive_time=checkout.isoformat(),
                    duration_hours=nights * 24.0,
                    url="https://example.invalid/hotel",
                    details={"nights": nights, "per_night": per_night},
                    stars=rnd.choices([2, 3, 4, 5], weights=[0.1, 0.35, 0.4, 0.15], k=1)[0],
                    rating=round(rnd.uniform(6.0, 9.8), 1),
                    wifi=rnd.random() < 0.85,
                    breakfast_included=rnd.random() < 0.5,
                    free_cancellation=rnd.random() < 0.6,
                    distance_km=round(rnd.uniform(0.1, 8.0), 1),
                    parking=rnd.random() < 0.4,
                    air_conditioning=rnd.random() < 0.7,
                    pets_allowed=rnd.random() < 0.3,
                    pool_or_fitness=rnd.random() < 0.35,
                ))
        return offers
