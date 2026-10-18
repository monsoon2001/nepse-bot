import pandas as pd

from nepse_sense.indicators.technical import atr, ema, macd, rsi_wilder


def test_ema_basic():
    s = pd.Series([1, 2, 3, 4, 5])
    result = ema(s, 3)
    assert len(result) == 5
    assert pd.notna(result.iloc[-1])


def test_rsi_wilder():
    s = pd.Series(range(1, 16))
    result = rsi_wilder(s, 14)
    assert pd.notna(result.iloc[-1])


def test_macd():
    s = pd.Series(range(1, 30), dtype=float)
    macd_line, signal_line, hist = macd(s)
    assert len(macd_line) == len(s)


def test_atr():
    high = pd.Series([10, 11, 12, 11, 12])
    low = pd.Series([9, 10, 11, 10, 11])
    close = pd.Series([9.5, 10.5, 11.5, 10.5, 11.5])
    result = atr(high, low, close, 3)
    assert len(result) == 5
