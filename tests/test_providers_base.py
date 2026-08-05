from datetime import date

from traveldeals.models import RoutePreference
from traveldeals.providers.base import date_candidates


def make_route(**overrides) -> RoutePreference:
    defaults = dict(id="r1", origin="BER", destination="BCN",
                     depart_date_from=date(2026, 9, 10), depart_date_until=date(2026, 9, 10))
    defaults.update(overrides)
    return RoutePreference(**defaults)


def test_single_day_route_with_no_flex_yields_exactly_one_day():
    route = make_route()
    assert date_candidates(route) == [date(2026, 9, 10)]


def test_flex_days_widen_the_window_on_both_sides():
    route = make_route(flex_days_before=1, flex_days_after=2)
    assert date_candidates(route) == [
        date(2026, 9, 9), date(2026, 9, 10), date(2026, 9, 11), date(2026, 9, 12),
    ]


def test_multi_day_date_range_without_flex():
    route = make_route(depart_date_from=date(2026, 9, 10), depart_date_until=date(2026, 9, 12))
    assert date_candidates(route) == [date(2026, 9, 10), date(2026, 9, 11), date(2026, 9, 12)]
