"""Extension points for real data sources.

Not implemented yet - v1 runs entirely on mock.py. Each class below is where
a real integration plugs in later; config.py will swap the mock class for
the matching real one here once credentials exist. Kept as explicit stubs
(rather than omitted) so the shape of "what needs an API key" is visible
from day one.
"""
from __future__ import annotations

import os

from traveldeals.models import Mode, Offer, RoutePreference
from traveldeals.providers.base import Provider


class AmadeusFlightProvider(Provider):
    """Flights via the Amadeus Self-Service Flight Offers Search API.
    Free tier exists (test environment, limited quota); needs
    AMADEUS_API_KEY / AMADEUS_API_SECRET. https://developers.amadeus.com
    """
    mode = Mode.FLIGHT

    def __init__(self):
        self.api_key = os.environ.get("AMADEUS_API_KEY")
        self.api_secret = os.environ.get("AMADEUS_API_SECRET")

    def search(self, route: RoutePreference) -> list[Offer]:
        if not (self.api_key and self.api_secret):
            return []
        raise NotImplementedError(
            "AMADEUS_API_KEY is set but the Amadeus adapter isn't wired up "
            "yet - implement OAuth2 token fetch + GET /v2/shopping/flight-offers here."
        )


class DeutscheBahnProvider(Provider):
    """Trains via DB. The official DB API portal (developers.deutschebahn.com)
    covers timetables/disruptions; full fare pricing typically needs the
    DB Vendo/HAFAS endpoints used by db-vendo-client (community project,
    unofficial) or a commercial distributor (e.g. via Trainline Partner API).
    """
    mode = Mode.TRAIN

    def __init__(self):
        self.client_id = os.environ.get("DB_API_CLIENT_ID")

    def search(self, route: RoutePreference) -> list[Offer]:
        if not self.client_id:
            return []
        raise NotImplementedError("DB_API_CLIENT_ID is set but the DB adapter isn't wired up yet.")


class FlixBusProvider(Provider):
    """Bus via FlixBus. No public self-serve API; requires a partner/
    affiliate agreement (https://www.flixbus.com/partnering-with-flixbus)."""
    mode = Mode.BUS

    def __init__(self):
        self.partner_token = os.environ.get("FLIXBUS_PARTNER_TOKEN")

    def search(self, route: RoutePreference) -> list[Offer]:
        if not self.partner_token:
            return []
        raise NotImplementedError("FLIXBUS_PARTNER_TOKEN is set but the FlixBus adapter isn't wired up yet.")


class BookingHotelProvider(Provider):
    """Hotels via Booking.com/Trivago-style affiliate feeds. Both require an
    approved affiliate/partner account (Booking.com Affiliate Partner
    Program, Trivago Publisher Program) - no open self-serve API."""
    mode = Mode.HOTEL

    def __init__(self):
        self.affiliate_id = os.environ.get("BOOKING_AFFILIATE_ID")

    def search(self, route: RoutePreference) -> list[Offer]:
        if not self.affiliate_id:
            return []
        raise NotImplementedError("BOOKING_AFFILIATE_ID is set but the Booking.com adapter isn't wired up yet.")
