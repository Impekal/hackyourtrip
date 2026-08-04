"""Provider abstraction.

A Provider searches one mode (flight/train/bus/hotel) for one RoutePreference
and returns a list of Offers. Swapping mock data for a real API later means
writing one new class here and pointing config.py at it - nothing else in the
engine, notifiers, or dashboard needs to change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from traveldeals.models import Mode, Offer, RoutePreference


class Provider(ABC):
    #: the Mode this provider answers for
    mode: Mode

    @abstractmethod
    def search(self, route: RoutePreference) -> list[Offer]:
        """Return candidate offers for the given route. Must not raise on
        "no results" - return an empty list instead."""
        raise NotImplementedError


class NotConfiguredProvider(Provider):
    """Stand-in for a real API adapter that needs credentials which aren't
    set up yet. Returns no offers instead of crashing the whole pipeline, so
    a route with a mix of mocked and real providers still produces results."""

    def __init__(self, mode: Mode, reason: str):
        self.mode = mode
        self.reason = reason

    def search(self, route: RoutePreference) -> list[Offer]:
        return []
