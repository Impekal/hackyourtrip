"""Core data model for HackYourTrip.

Everything the user can configure per tracked route, and everything a
provider/engine hands back, lives here as plain dataclasses so the rest of
the codebase (providers, engine, notifiers, dashboard) shares one vocabulary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class Priority(str, Enum):
    CHEAPEST = "cheapest"
    FASTEST = "fastest"
    BEST_VALUE = "best_value"  # weighted price/duration tradeoff


class Mode(str, Enum):
    FLIGHT = "flight"
    TRAIN = "train"
    BUS = "bus"
    HOTEL = "hotel"
    FLIGHT_HOTEL = "flight_hotel"
    TRAIN_HOTEL = "train_hotel"
    BUS_HOTEL = "bus_hotel"
    TRAIN_OR_BUS = "train_or_bus"  # whichever of the two is better


# Modes that are pure transport (as opposed to hotel-only or combos)
TRANSPORT_MODES = (Mode.FLIGHT, Mode.TRAIN, Mode.BUS)


@dataclass
class BaggagePref:
    carry_on_only: bool = False
    checked_bags: int = 0
    checked_bag_kg: int = 23


@dataclass
class RailPref:
    """Germany-specific rail discounts the engine should factor into price."""
    bahncard: Optional[str] = None  # "25", "50", "100" or None
    deutschlandticket: bool = False


@dataclass
class RoutePreference:
    id: str
    origin: str
    destination: str
    depart_date_from: date
    depart_date_until: date
    flex_days_before: int = 0
    flex_days_after: int = 0
    min_nights: int = 0
    max_nights: int = 0
    budget: Optional[float] = None
    currency: str = "EUR"
    max_duration_hours: Optional[float] = None
    priority: Priority = Priority.BEST_VALUE
    modes: list[Mode] = field(default_factory=lambda: [Mode.FLIGHT])
    baggage: BaggagePref = field(default_factory=BaggagePref)
    rail: RailPref = field(default_factory=RailPref)
    low_cost_airlines_ok: bool = True
    notes: str = ""


@dataclass
class Offer:
    """A single priced option from one provider for one mode."""
    mode: Mode
    provider: str
    booking_site: str
    price: float
    currency: str
    depart_time: str  # ISO datetime
    arrive_time: str  # ISO datetime
    duration_hours: float
    url: str = ""
    checked_bag_fee: float = 0.0  # cost to add the user's requested checked bag(s)
    is_low_cost: bool = False
    details: dict = field(default_factory=dict)


@dataclass
class TripOption:
    """One or more Offers combined into something the user can book (or a
    single Offer for non-combo modes), ranked and annotated by the engine."""
    mode: Mode
    offers: list[Offer]
    total_price: float
    currency: str
    total_duration_hours: float
    score: float
    is_error_fare: bool = False
    is_price_drop: bool = False
    recommendations: list[str] = field(default_factory=list)

    @property
    def booking_sites(self) -> list[str]:
        return [o.booking_site for o in self.offers]
