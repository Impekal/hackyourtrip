from datetime import date
from pathlib import Path

from traveldeals.config import load_routes


def test_round_trip_and_return_date_parsed(tmp_path: Path):
    yaml_content = """
routes:
  - id: r1
    origin: BER
    destination: BCN
    depart_date_from: 2026-09-10
    depart_date_until: 2026-09-10
    round_trip: true
    return_date: 2026-09-17
"""
    path = tmp_path / "routes.yaml"
    path.write_text(yaml_content)
    routes = load_routes(path)
    assert len(routes) == 1
    assert routes[0].round_trip is True
    assert routes[0].return_date == date(2026, 9, 17)


def test_round_trip_defaults_to_false_without_return_date(tmp_path: Path):
    yaml_content = """
routes:
  - id: r1
    origin: BER
    destination: BCN
    depart_date_from: 2026-09-10
    depart_date_until: 2026-09-10
"""
    path = tmp_path / "routes.yaml"
    path.write_text(yaml_content)
    routes = load_routes(path)
    assert routes[0].round_trip is False
    assert routes[0].return_date is None


def test_baggage_carry_on_fields_parsed(tmp_path: Path):
    yaml_content = """
routes:
  - id: r1
    origin: BER
    destination: BCN
    depart_date_from: 2026-09-10
    depart_date_until: 2026-09-10
    baggage:
      checked_bags: 2
      checked_bag_kg: 23
      carry_on_count: 2
      carry_on_max_kg: 10
"""
    path = tmp_path / "routes.yaml"
    path.write_text(yaml_content)
    routes = load_routes(path)
    baggage = routes[0].baggage
    assert baggage.checked_bags == 2
    assert baggage.checked_bag_kg == 23
    assert baggage.carry_on_count == 2
    assert baggage.carry_on_max_kg == 10.0


def test_baggage_defaults_without_baggage_section(tmp_path: Path):
    yaml_content = """
routes:
  - id: r1
    origin: BER
    destination: BCN
    depart_date_from: 2026-09-10
    depart_date_until: 2026-09-10
"""
    path = tmp_path / "routes.yaml"
    path.write_text(yaml_content)
    baggage = load_routes(path)[0].baggage
    assert baggage.carry_on_count == 1
    assert baggage.carry_on_max_kg == 8.0
