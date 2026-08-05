from traveldeals.providers.geo import estimate_direct_flight_duration_hours


def test_known_route_returns_plausible_estimate():
    # BER-BCN is a real ~1.9h-2.5h direct flight in practice
    estimate = estimate_direct_flight_duration_hours("BER", "BCN")
    assert estimate is not None
    assert 1.5 < estimate < 3.5


def test_same_airport_returns_just_the_overhead():
    estimate = estimate_direct_flight_duration_hours("BER", "BER")
    assert estimate == 0.5


def test_unknown_airport_returns_none():
    assert estimate_direct_flight_duration_hours("ZZZ", "BER") is None
    assert estimate_direct_flight_duration_hours("BER", "ZZZ") is None


def test_is_case_insensitive():
    assert estimate_direct_flight_duration_hours("ber", "bcn") == estimate_direct_flight_duration_hours("BER", "BCN")


def test_longer_distance_gives_longer_estimate():
    short = estimate_direct_flight_duration_hours("BER", "MUC")
    long = estimate_direct_flight_duration_hours("BER", "SYD")
    assert short < long
