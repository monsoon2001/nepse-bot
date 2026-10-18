import pandas as pd

from nepse_sense.indicators.technical import ema, rsi_wilder


def test_ema_reference():
    # Simple known values
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    result = ema(s, 3)
    # EMA with span=3, adjust=False - first value is same as input for this method
    assert abs(result.iloc[0] - s.iloc[0]) < 0.001
    assert pd.notna(result.iloc[-1])


def test_rsi_wilder_reference():
    s = pd.Series([44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
                   45.89, 46.03, 45.61, 46.28, 46.28])
    result = rsi_wilder(s, 14)
    # Wilder RSI calculation - last value should be reasonable
    assert 0 <= result.iloc[-1] <= 100
