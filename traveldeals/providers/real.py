"""Extension points for real data sources that aren't wired up yet.

v1 runs these as mock.py; providers/amadeus.py has since become the first
fully-implemented real adapter (see that module) - config.py/cli.py swap it
in for MockFlightProvider once AMADEUS_API_KEY/SECRET are set. The classes
below are still stubs, kept explicit (rather than omitted) so the shape of
"what needs an API key" is visible from day one.
"""
from __future__ import annotations

import os

from traveldeals.models import Mode, Offer, RoutePreference
from traveldeals.providers.base import Provider


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
