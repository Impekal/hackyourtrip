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
    """How results get ranked. Everything here is a *sort order*: the engine
    always scores lower-is-better, so e.g. MOST_EXPENSIVE negates the price."""
    CHEAPEST = "cheapest"
    MOST_EXPENSIVE = "most_expensive"   # price descending
    FASTEST = "fastest"
    EXACT_DATE = "exact_date"           # least deviation from the wanted date first
    BEST_VALUE = "best_value"           # weighted price/duration/comfort tradeoff


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
    """Checked bags and carry-on tracked separately, each with their own
    weight-per-piece and count - matches how airlines actually price/allow
    baggage (a fixed checked-bag allowance plus a much smaller cabin
    allowance), rather than a single carry-on-only yes/no toggle.

    Both *_kg fields are Optional: None means "egal" (no preference stated),
    distinct from checked_bags/carry_on_count == 0 which means "none of
    these needed at all"."""
    checked_bags: int = 0
    checked_bag_kg: Optional[float] = 23
    carry_on_count: int = 1
    carry_on_max_kg: Optional[float] = 8.0


@dataclass
class RailPref:
    """Germany-specific rail discounts the engine should factor into price."""
    bahncard: Optional[str] = None  # "25", "50", "100" or None
    deutschlandticket: bool = False


# Meal-plan tiers, ordered low to high - min_meal_plan below is satisfied by
# an offer whose tier index is >= the requested tier's index (an offer with
# all_inclusive also satisfies a "breakfast" requirement, for example).
MEAL_PLAN_TIERS = ["none", "breakfast", "half_board", "full_board", "all_inclusive"]

# Free-text-ish but constrained property types - matches the filter Trivago
# itself exposes; empty list on HotelPref.property_types means "any type".
PROPERTY_TYPES = ["hotel", "apartment", "hostel", "resort", "bnb", "guesthouse", "villa"]


@dataclass
class HotelPref:
    """Hard filters for hotel offers - the full amenity set a real Trivago
    search exposes (not just a handful), which also get folded into the
    best_value comfort score (see engine.py) rather than only used to
    filter."""
    min_stars: Optional[int] = None
    min_rating: Optional[float] = None       # 0..10
    max_distance_km: Optional[float] = None  # to city center/station/airport
    property_types: list[str] = field(default_factory=list)  # subset of PROPERTY_TYPES, [] = any
    min_meal_plan: Optional[str] = None  # one of MEAL_PLAN_TIERS, None = no requirement
    require_wifi: bool = False
    require_free_cancellation: bool = False
    require_parking: bool = False
    require_air_conditioning: bool = False
    require_pets_allowed: bool = False
    require_pool: bool = False
    require_gym: bool = False
    require_spa: bool = False
    require_restaurant: bool = False
    require_bar: bool = False
    require_room_service: bool = False
    require_24h_front_desk: bool = False
    require_business_facilities: bool = False
    require_laundry_service: bool = False
    require_elevator: bool = False
    require_balcony_or_terrace: bool = False
    require_kitchen: bool = False
    require_beachfront: bool = False
    require_disabled_access: bool = False
    require_ev_charging: bool = False
    require_bicycle_rental: bool = False
    require_babysitting: bool = False
    require_sauna: bool = False
    require_hot_tub: bool = False
    require_non_smoking: bool = False
    require_family_rooms: bool = False
    require_airport_shuttle: bool = False


@dataclass
class TransportPref:
    """Hard filters/comfort factors for flight/train/bus offers, beyond
    price/duration/baggage."""
    direct_only: bool = False
    require_wifi_onboard: bool = False
    require_power_outlets: bool = False
    min_punctuality_pct: Optional[float] = None
    # Time-of-day window, independent of flex_days_before/after (which
    # widens the set of candidate *dates*): "I want to leave around 09:00,
    # +/- 90 minutes is fine" - None means no time-of-day preference at all.
    preferred_depart_time: Optional[str] = None  # "HH:MM"
    depart_time_flex_minutes: int = 0


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
    # "any" = alle Anbieter, "only" = ausschließlich Low-Cost,
    # "exclude" = keine Low-Cost. Ersetzt das frühere
    # low_cost_airlines_ok-Flag, das kein "nur Low-Cost" ausdrücken konnte.
    low_cost: str = "any"
    # Only meaningful for flight/train/bus (and their OR-combos) - *_hotel
    # combos already have an implicit return via checkin+nights, and Hotel
    # has no transport leg at all.
    round_trip: bool = False
    return_date: Optional[date] = None
    # True = only show offers that actually look like a deal (see
    # engine._is_deal): flagged as a price drop/error fare by the price
    # history, or notably below the median of what this search found.
    # False = show everything, deal or not.
    deals_only: bool = False
    notes: str = ""


@dataclass
class Offer:
    """A single priced option from one provider for one mode.

    Fields below `is_low_cost` are mode-specific and simply unset/default
    for modes they don't apply to: `stops`/`wifi_onboard`/`power_outlets`/
    `legroom_cm`/`punctuality_pct` are transport-only (flight/train/bus);
    everything under "hotel amenities" below (property_type, meal_plan,
    free_cancellation, distance_km, and the full amenity flag set) is
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
    # Set only for round-trip offers: `price` is then the combined total for
    # both legs, and this is the return leg's departure time.
    return_depart_time: Optional[str] = None

    # transport comfort
    stops: int = 0
    wifi_onboard: bool = False
    power_outlets: bool = False
    legroom_cm: Optional[float] = None
    punctuality_pct: Optional[float] = None

    # hotel amenities
    stars: Optional[int] = None
    rating: Optional[float] = None  # 0..10
    property_type: str = "hotel"    # one of PROPERTY_TYPES
    meal_plan: str = "none"         # one of MEAL_PLAN_TIERS
    free_cancellation: bool = False
    distance_km: Optional[float] = None
    parking: bool = False
    air_conditioning: bool = False
    pets_allowed: bool = False
    pool: bool = False
    gym: bool = False
    spa: bool = False
    restaurant: bool = False
    bar: bool = False
    room_service: bool = False
    front_desk_24h: bool = False
    business_facilities: bool = False
    laundry_service: bool = False
    elevator: bool = False
    balcony_or_terrace: bool = False
    kitchen: bool = False
    beachfront: bool = False
    disabled_access: bool = False
    ev_charging: bool = False
    bicycle_rental: bool = False
    babysitting: bool = False
    sauna: bool = False
    hot_tub: bool = False
    non_smoking: bool = False
    family_rooms: bool = False
    airport_shuttle: bool = False
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
    # Notably cheaper than the median of this same search - the only "deal"
    # signal available before any price history exists.
    is_below_median: bool = False
    recommendations: list[str] = field(default_factory=list)

    @property
    def is_deal(self) -> bool:
        return self.is_error_fare or self.is_price_drop or self.is_below_median

    @property
    def booking_sites(self) -> list[str]:
        return [o.booking_site for o in self.offers]
