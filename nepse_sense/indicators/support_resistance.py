from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


class Zone:
    def __init__(self, price: float, touches: int = 1, strength: float = 1.0):
        self.price = price
        self.touches = touches
        self.strength = strength


def find_pivots(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 5) -> dict:
    high_pivots = []
    low_pivots = []
    for i in range(window, len(high) - window):
        if high.iloc[i] == high.iloc[i - window : i + window + 1].max():
            high_pivots.append((i, high.iloc[i]))
        if low.iloc[i] == low.iloc[i - window : i + window + 1].min():
            low_pivots.append((i, low.iloc[i]))
    return {"highs": high_pivots, "lows": low_pivots}


def cluster_pivots(pivots: list[tuple], tolerance: float = 0.02) -> list[dict[str, Any]]:
    if not pivots:
        return []
    clusters = []
    pivots_sorted = sorted(pivots, key=lambda x: x[1])
    current = [pivots_sorted[0]]
    for p in pivots_sorted[1:]:
        if p[1] / current[0][1] <= 1 + tolerance and p[1] / current[0][1] >= 1 - tolerance:
            current.append(p)
        else:
            price = float(np.mean([c[1] for c in current]))
            touches = len(current)
            clusters.append({"price": price, "touches": touches, "strength": touches / 3.0})
            current = [p]
    if current:
        price = float(np.mean([c[1] for c in current]))
        touches = len(current)
        clusters.append({"price": price, "touches": touches, "strength": touches / 3.0})
    return clusters


def get_support_resistance_zones(
    df: pd.DataFrame, tolerance: float = 0.02, min_touches: int = 2
) -> dict[str, list[dict[str, Any]]]:
    pivots = find_pivots(df["high"], df["low"], df["close"])
    all_clusters = cluster_pivots(pivots["highs"] + pivots["lows"], tolerance)
    zones = []
    for c in all_clusters:
        if c["touches"] >= min_touches:
            zones.append(c)
    current_price = df["close"].iloc[-1] if len(df) > 0 else 0
    support = [z for z in zones if z["price"] < current_price]
    resistance = [z for z in zones if z["price"] > current_price]
    support.sort(key=lambda x: x["price"], reverse=True)
    resistance.sort(key=lambda x: x["price"])
    return {"support": support[:5], "resistance": resistance[:5], "zones": zones}
