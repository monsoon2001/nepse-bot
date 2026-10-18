from __future__ import annotations

import json

import pandas as pd

from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import IndicatorDaily, PriceDaily
from nepse_sense.indicators.support_resistance import get_support_resistance_zones
from nepse_sense.indicators.technical import (
    atr,
    ema,
    macd,
    relative_volume,
    rolling_high,
    rolling_low,
    rsi_wilder,
)


class IndicatorCalculator:
    def __init__(self):
        self.db = SessionLocal()

    def __del__(self):
        try:
            self.db.close()
        except Exception:
            from nepse_sense.logging import logger

            logger.debug("Error closing db in IndicatorCalculator")

    def calculate_for_symbol(self, symbol: str, min_bars: int = 50):
        prices = (
            self.db.query(PriceDaily)
            .filter(PriceDaily.symbol == symbol)
            .order_by(PriceDaily.date.asc())
            .all()
        )
        if len(prices) < min_bars:
            return 0
        df = pd.DataFrame(
            {
                "date": [p.date for p in prices],
                "open": [p.open or 0 for p in prices],
                "high": [p.high or 0 for p in prices],
                "low": [p.low or 0 for p in prices],
                "close": [p.close or 0 for p in prices],
                "volume": [p.volume or 0 for p in prices],
            }
        )
        df.set_index("date", inplace=True)
        df = df.dropna()
        if len(df) < min_bars:
            return 0
        ema20 = ema(df["close"], 20)
        ema50 = ema(df["close"], 50)
        rsi = rsi_wilder(df["close"], 14)
        macd_line, macd_signal, macd_hist = macd(df["close"])
        atr14 = atr(df["high"], df["low"], df["close"], 14)
        rel_vol = relative_volume(df["volume"], 20)
        high_52w = rolling_high(df["close"], 252)
        low_52w = rolling_low(df["close"], 252)
        sr = get_support_resistance_zones(df)

        def _f(s: pd.Series, i: int) -> float | None:
            v = s.iloc[i]
            return float(v) if pd.notna(v) else None

        count = 0
        for idx in range(max(51, len(df) - 30), len(df)):
            date_idx = df.index[idx]
            ind = IndicatorDaily(
                symbol=symbol,
                date=date_idx,
                ema20=_f(ema20, idx),
                ema50=_f(ema50, idx),
                rsi14=_f(rsi, idx),
                macd_line=_f(macd_line, idx),
                macd_signal=_f(macd_signal, idx),
                macd_hist=_f(macd_hist, idx),
                atr14=_f(atr14, idx),
                rel_volume=_f(rel_vol, idx),
                high_52w=_f(high_52w, idx),
                low_52w=_f(low_52w, idx),
                indicators=json.dumps(
                    {"ema20": _f(ema20, idx), "ema50": _f(ema50, idx), "rsi14": _f(rsi, idx)}
                ),
                zones=json.dumps(sr),
            )
            self.db.add(ind)
            count += 1
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
        return count

    def calculate_all(self, min_bars: int = 50):
        symbols = self.db.query(PriceDaily.symbol).distinct().all()
        total = 0
        for (symbol,) in symbols:
            total += self.calculate_for_symbol(symbol, min_bars)
        return total
