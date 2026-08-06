"""Provider abstraction.

A Provider searches one mode (flight/train/bus/hotel) for one RoutePreference
and returns a list of Offers. Swapping mock data for a real API later means
writing one new class here and pointing config.py at it - nothing else in the
engine, notifiers, or dashboard needs to change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import date, timedelta

from traveldeals.models import Mode, Offer, RoutePreference


def date_candidates(route: RoutePreference) -> list[date]:
    """Every day a route's flex window covers - shared by any provider that
    needs to enumerate candidate travel/check-in dates (mock and real alike)."""
    start = route.depart_date_from - timedelta(days=route.flex_days_before)
    end = route.depart_date_until + timedelta(days=route.flex_days_after)
    days = (end - start).days
    return [start + timedelta(days=i) for i in range(days + 1)]


class Provider(ABC):
    #: the Mode this provider answers for
    mode: Mode

    @abstractmethod
    def search(self, route: RoutePreference) -> list[Offer]:
        """Return candidate offers for the given route. Must not raise on
        "no results" - return an empty list instead."""
        raise NotImplementedError


class CompositeProvider(Provider):
    """Merges several providers for one mode into a single offer pool.

    No free source covers a mode on its own: Travelpayouts knows many
    airlines but only as a cache of recently *seen* fares, while Ryanair
    returns live bookable prices for its own routes and nothing else. Asking
    both and merging is strictly better than choosing one.

    A failing provider must not take the others down with it - a partial
    result beats an empty one, and every mode already copes with "no offers".
    """

    def __init__(self, mode: Mode, providers: list[Provider]):
        self.mode = mode
        self.providers = providers

    def search(self, route: RoutePreference) -> list[Offer]:
        offers: list[Offer] = []
        seen: set[tuple] = set()
        for provider in self.providers:
            try:
                found = provider.search(route)
            except Exception as exc:  # noqa: BLE001 - one bad source must not sink the search
                print(f"[composite] {type(provider).__name__} failed: {exc}")
                continue
            for offer in found:
                # The same flight can appear in both pools; keep the first.
                key = (offer.depart_time, offer.booking_site, round(offer.price, 2))
                if key in seen:
                    continue
                seen.add(key)
                offers.append(offer)
        return offers


class NearbyStationsProvider(Provider):
    """NearbyAirportsProvider for the ground modes.

    Stations need their own wrapper because there is no coordinate table for
    them: each candidate is resolved through Transitous, which returns the
    real stop with real coordinates. Faking a table from airport positions
    would misstate the detour by however far a city's station sits from its
    airport.
    """

    def __init__(self, mode: Mode, inner: Provider, limit_per_side: int = 2):
        self.mode = mode
        self.inner = inner
        self.limit_per_side = limit_per_side

    def search(self, route: RoutePreference) -> list[Offer]:
        offers = list(self.inner.search(route))
        if not route.nearby_km:
            return offers

        from traveldeals.providers.transitous import (TransitousTrainProvider,
                                                       nearby_stations)
        resolver = TransitousTrainProvider()
        origins = [(route.origin, 0)] + nearby_stations(resolver, route.origin, route.nearby_km, self.limit_per_side)
        destinations = [(route.destination, 0)] + nearby_stations(resolver, route.destination, route.nearby_km, self.limit_per_side)

        for origin, origin_km in origins:
            for destination, destination_km in destinations:
                if origin_km == 0 and destination_km == 0:
                    continue
                variant = replace(route, origin=origin, destination=destination)
                try:
                    found = self.inner.search(variant)
                except Exception as exc:  # noqa: BLE001
                    print(f"[nearby-stations] {origin}->{destination} failed: {exc}")
                    continue
                for offer in found:
                    offer.alt_origin = origin if origin_km else ""
                    offer.alt_destination = destination if destination_km else ""
                    offer.detour_km = origin_km + destination_km
                    offers.append(offer)
        return offers


class NotConfiguredProvider(Provider):
    """Stand-in for a real API adapter that needs credentials which aren't
    set up yet. Returns no offers instead of crashing the whole pipeline, so
    a route with a mix of mocked and real providers still produces results."""

    def __init__(self, mode: Mode, reason: str):
        self.mode = mode
        self.reason = reason

    def search(self, route: RoutePreference) -> list[Offer]:
        return []


class NearbyAirportsProvider(Provider):
    """Runs an inner provider again for airports near origin/destination.

    Hamburg->Lyon has almost no fares. Bremen->Geneva might, and 103 km of
    driving for a 100 EUR saving is a trade some travellers take gladly and
    others refuse - which is exactly why the tool must *offer* it with the
    detour spelled out rather than decide for them.

    Every offer from an alternative airport is tagged (`alt_origin` /
    `alt_destination` / `detour_km`) so nothing can quietly look like a
    departure from the airport that was actually searched for.
    """

    def __init__(self, mode: Mode, inner: Provider, limit_per_side: int = 2):
        self.mode = mode
        self.inner = inner
        self.limit_per_side = limit_per_side

    def search(self, route: RoutePreference) -> list[Offer]:
        offers = list(self.inner.search(route))
        if not route.nearby_km:
            return offers

        # Imported here to keep providers/base free of a hard geo dependency
        # for callers that never use this wrapper.
        from traveldeals.providers.geo import nearby_airports

        origins = [(route.origin, 0)] + nearby_airports(route.origin, route.nearby_km, self.limit_per_side)
        destinations = [(route.destination, 0)] + nearby_airports(route.destination, route.nearby_km, self.limit_per_side)

        for origin, origin_km in origins:
            for destination, destination_km in destinations:
                if origin_km == 0 and destination_km == 0:
                    continue  # already searched above
                variant = replace(route, origin=origin, destination=destination)
                try:
                    found = self.inner.search(variant)
                except Exception as exc:  # noqa: BLE001 - one variant must not sink the search
                    print(f"[nearby] {origin}->{destination} failed: {exc}")
                    continue
                for offer in found:
                    offer.alt_origin = origin if origin_km else ""
                    offer.alt_destination = destination if destination_km else ""
                    offer.detour_km = origin_km + destination_km
                    offers.append(offer)
        return offers
