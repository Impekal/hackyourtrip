from datetime import date

from traveldeals.pricehistory import PriceHistory


def test_needs_at_least_three_observations(tmp_path):
    hist = PriceHistory(tmp_path / "history.json")
    hist.record("r1", "flight", 100, "EUR", date(2026, 1, 1))
    hist.record("r1", "flight", 100, "EUR", date(2026, 1, 2))
    is_drop, is_error = hist.is_notable_low("r1", "flight", 10)
    assert (is_drop, is_error) == (False, False)


def test_detects_price_drop_and_error_fare(tmp_path):
    hist = PriceHistory(tmp_path / "history.json")
    for i, price in enumerate([100, 110, 105, 95]):
        hist.record("r1", "flight", price, "EUR", date(2026, 1, 1 + i))

    is_drop, is_error = hist.is_notable_low("r1", "flight", 80)
    # median of [100,110,105,95] = 102.5 -> *0.85 = 87.125, 80 <= that -> drop
    assert is_drop is True
    assert is_error is False  # min(95)*0.5=47.5, 80 is not below that

    is_drop, is_error = hist.is_notable_low("r1", "flight", 20)
    assert is_error is True


def test_stats_and_persistence(tmp_path):
    path = tmp_path / "history.json"
    hist = PriceHistory(path)
    hist.record("r1", "flight", 100, "EUR", date(2026, 1, 1))
    hist.record("r1", "flight", 200, "EUR", date(2026, 1, 2))
    hist.save()

    reloaded = PriceHistory(path)
    stats = reloaded.stats("r1", "flight")
    assert stats == {"count": 2, "min": 100, "max": 200, "median": 150}


def test_record_same_day_overwrites_not_duplicates(tmp_path):
    hist = PriceHistory(tmp_path / "history.json")
    hist.record("r1", "flight", 100, "EUR", date(2026, 1, 1))
    hist.record("r1", "flight", 120, "EUR", date(2026, 1, 1))
    stats = hist.stats("r1", "flight")
    assert stats["count"] == 1
    assert stats["min"] == 120
