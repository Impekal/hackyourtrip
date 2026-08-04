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
    BEST_VALUE = "best_value"  # weighted price/duration/comfort tradeoff


class Mode(str, Enum):
    FLIGHT = "flight"
    TRAIN = "train"
    BUS = "bus"
    HOTEL = "hotel"
    FLIGHT_HOTEL = "flight_hotel"
    TRAIN_HOTEL = "train_hotel"
    BUS_HOTEL = "bus_hotel"
    TRAIN_OR_BUS = "train_or_bus"      # whichever of the two is better
    FLIGHT_OR_TRAIN = "flight_or_train"
    FLIGHT_OR_BUS = "flight_or_bus"


# Modes that are pure transport (as opposed to hotel-only or combos)
TRANSPORT_MODES = (Mode.FLIGHT, Mode.TRAIN, Mode.BUS)

# "whichever of these two transport modes is better" combos -> the two pools
# the engine should merge and rank together.
OR_COMBO_MODES = {
    Mode.TRAIN_OR_BUS: (Mode.TRAIN, Mode.BUS),
    Mode.FLIGHT_OR_TRAIN: (Mode.FLIGHT, Mode.TRAIN),
    Mode.FLIGHT_OR_BUS: (Mode.FLIGHT, Mode.BUS),
}


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
class HotelPref:
    """Hard filters for hotel offers - beyond what a typical Trivago search
    exposes, these get folded into the best_value comfort score too (see
    engine.py) rather than only used to filter."""
    min_stars: Optional[int] = None
    min_rating: Optional[float] = None       # 0..10
    max_distance_km: Optional[float] = None  # to city center/station/airport
    require_wifi: bool = False
    require_breakfast: bool = False
    require_free_cancellation: bool = False
    require_parking: bool = False
    require_air_conditioning: bool = False
    require_pets_allowed: bool = False
    require_pool_or_fitness: bool = False


@dataclass
class TransportPref:
    """Hard filters/comfort factors for flight/train/bus offers, beyond
    price/duration/baggage."""
    direct_only: bool = False
    require_wifi_onboard: bool = False
    require_power_outlets: bool = False
    min_punctuality_pct: Optional[float] = None


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
    hotel: HotelPref = field(default_factory=HotelPref)
    transport: TransportPref = field(default_factory=TransportPref)
    low_cost_airlines_ok: bool = True
    notes: str = ""


@dataclass
class Offer:
    """A single priced option from one provider for one mode.

    Fields below `is_low_cost` are mode-specific and simply unset/default
    for modes they don't apply to: `stops`/`wifi_onboard`/`power_outlets`/
    `legroom_cm`/`punctuality_pct` are transport-only (flight/train/bus);
    `stars`/`rating`/`breakfast_included`/`free_cancellation`/`distance_km`/
    `parking`/`air_conditioning`/`pets_allowed`/`pool_or_fitness` are
    hotel-only. `wifi` is shared (onboard wifi for transport, room wifi for
    hotels) since it's the same concept either way.
    """
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

    # transport comfort
    stops: int = 0
    wifi_onboard: bool = False
    power_outlets: bool = False
    legroom_cm: Optional[float] = None
    punctuality_pct: Optional[float] = None

    # hotel amenities
    stars: Optional[int] = None
    rating: Optional[float] = None  # 0..10
    breakfast_included: bool = False
    free_cancellation: bool = False
    distance_km: Optional[float] = None
    parking: bool = False
    air_conditioning: bool = False
    pets_allowed: bool = False
    pool_or_fitness: bool = False
    wifi: bool = False

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
