from traveldeals.currency import convert

RATES = {"EUR": 1.0, "USD": 1.1, "GBP": 0.85}


def test_same_currency_is_noop():
    assert convert(100, "EUR", "EUR", RATES) == 100


def test_convert_eur_to_usd():
    assert convert(100, "EUR", "USD", RATES) == 110.0


def test_convert_between_non_eur_currencies():
    # 85 GBP -> EUR (85/0.85=100) -> USD (100*1.1=110)
    assert convert(85, "GBP", "USD", RATES) == 110.0


def test_unknown_currency_returns_amount_unchanged():
    assert convert(50, "XXX", "USD", RATES) == 50
