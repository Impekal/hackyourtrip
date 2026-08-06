"""Provider abstraction.

A Provider searches one mode (flight/train/bus/hotel) for one RoutePreference
and returns a list of Offers. Swapping mock data for a real API later means
writing one new class here and pointing config.py at it - nothing else in the
engine, notifiers, or dashboard needs to change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
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


class NotConfiguredProvider(Provider):
    """Stand-in for a real API adapter that needs credentials which aren't
    set up yet. Returns no offers instead of crashing the whole pipeline, so
    a route with a mix of mocked and real providers still produces results."""

    def __init__(self, mode: Mode, reason: str):
        self.mode = mode
        self.reason = reason

    def search(self, route: RoutePreference) -> list[Offer]:
        return []
