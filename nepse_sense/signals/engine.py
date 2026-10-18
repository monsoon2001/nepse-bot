from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import yaml

from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import DataQualityIssue, IndicatorDaily, PriceCanonical
from nepse_sense.logging import logger


@dataclass
class SignalResult:
    symbol: str
    date: date
    category: str
    score: float
    reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    confidence_tier: str = "low"
    key_levels: dict = field(default_factory=dict)
    data_asof: date | None = None
    sources: list[str] = field(default_factory=list)


class SignalEngine:
    def __init__(self, config_path: str = "config/signals.yaml"):
        self.config = self._load_config(config_path)
        self.db = SessionLocal()

    def __del__(self):
        try:
            self.db.close()
        except Exception:
            from nepse_sense.logging import logger

            logger.debug("Error closing db in SignalEngine")

    def _load_config(self, path: str) -> dict:
        try:
            with open(path) as f:
                return yaml.safe_load(f)
        except Exception:
            logger.warning("signals.yaml not found, using defaults")
            return {
                "categories": {
                    "buy_candidate_min": 60,
                    "buy_watch_min": 35,
                    "sell_review_max": 25,
                },
                "confidence_tiers": {"high_min": 70, "medium_min": 40},
                "weights": {},
                "risk_flags": [],
            }

    def _has_critical_issues(self, symbol: str, dt: date) -> bool:
        issues = (
            self.db.query(DataQualityIssue)
            .filter(
                DataQualityIssue.symbol == symbol,
                DataQualityIssue.date <= dt,
                DataQualityIssue.severity == "critical",
                DataQualityIssue.resolved.is_(False),
            )
            .all()
        )
        return len(issues) > 0

    def _enough_history(self, symbol: str, dt: date, min_bars: int = 50) -> bool:
        count = (
            self.db.query(PriceCanonical)
            .filter(
                PriceCanonical.symbol == symbol,
                PriceCanonical.date <= dt,
            )
            .count()
        )
        return count >= min_bars

    def _is_stale(self, dt: date, current_date: date) -> bool:
        if current_date.weekday() in (0, 1, 2, 3):  # Mon-Thu approx check
            last_expected = current_date
        else:
            last_expected = current_date
        return dt < last_expected - timedelta(days=3)

    def evaluate_symbol(self, symbol: str, dt: date) -> SignalResult | None:
        # Check gating conditions first
        if self._has_critical_issues(symbol, dt):
            logger.info(f"Excluded {symbol}: unresolved critical data quality issues")
            return None
        if not self._enough_history(symbol, dt):
            logger.info(f"Excluded {symbol}: insufficient history")
            return None
        indicator = (
            self.db.query(IndicatorDaily)
            .filter(IndicatorDaily.symbol == symbol, IndicatorDaily.date == dt)
            .first()
        )
        if not indicator:
            logger.info(f"Excluded {symbol}: no indicator data for {dt}")
            return None
        canonical = (
            self.db.query(PriceCanonical)
            .filter(PriceCanonical.symbol == symbol, PriceCanonical.date == dt)
            .first()
        )
        if not canonical:
            return None
        if self._is_stale(canonical.date, date.today()):
            logger.info(f"Excluded {symbol}: stale data")
            return None
        weights = self.config.get("weights", {})
        score = 0.0
        reasons: list[str] = []
        risk_flags: list[str] = []
        close = canonical.close or 0
        ema20 = indicator.ema20 or 0
        ema50 = indicator.ema50 or 0
        rsi = indicator.rsi14 if indicator.rsi14 is not None else 50
        macd_line = indicator.macd_line or 0
        macd_signal = indicator.macd_signal or 0
        rel_volume = indicator.rel_volume or 0
        # EMA trend
        if close > ema20 and ema20 > ema50:
            w = weights.get("ema_trend_bullish", 15)
            score += w
            reasons.append(
                f"Bullish trend: price {close:.2f} > EMA20 {ema20:.2f} > EMA50 {ema50:.2f} (+{w})"
            )
        elif close < ema20 and ema20 < ema50:
            w = weights.get("ema_trend_bearish", -15)
            score += w
            reasons.append(
                f"Bearish trend: price {close:.2f} < EMA20 {ema20:.2f} < EMA50 {ema50:.2f} ({w})"
            )
        # RSI reversal
        if rsi < 30:
            w = weights.get("rsi_reversal_up", 12)
            score += w
            reasons.append(
                f"RSI oversold: {rsi:.1f} (<30, potential reversal up) (+{w})"
            )
        elif rsi > 70:
            w = weights.get("rsi_reversal_down", -12)
            score += w
            reasons.append(f"RSI overbought: {rsi:.1f} (>70, potential reversal down) ({w})")
        # MACD
        if macd_line > macd_signal and macd_line > 0:
            w = weights.get("macd_crossover_up", 10)
            score += w
            reasons.append(f"MACD bullish: line {macd_line:.3f} > signal {macd_signal:.3f} (+{w})")
        elif macd_line < macd_signal and macd_line < 0:
            w = weights.get("macd_crossover_down", -10)
            score += w
            reasons.append(f"MACD bearish: line {macd_line:.3f} < signal {macd_signal:.3f} ({w})")
        # Relative volume
        if rel_volume > 1.5:
            w = weights.get("high_relative_volume", 8)
            score += w
            reasons.append(f"High relative volume: {rel_volume:.2f}x average (+{w})")
        # S/R zones
        zones = indicator.zones or {}
        if isinstance(zones, str):
            import json

            zones = json.loads(zones)
        support_zones = zones.get("support", [])
        resistance_zones = zones.get("resistance", [])
        if support_zones:
            nearest = support_zones[0]
            dist = abs(close - nearest["price"]) / (close + 1e-10) * 100
            if dist < 2.0:
                w = weights.get("near_support", 7)
                score += w
                reasons.append(f"Near support: {nearest['price']:.2f} ({dist:.1f}% away) (+{w})")
            elif dist > 2.0 and close > nearest["price"]:
                pass
        if resistance_zones:
            nearest = resistance_zones[0]
            dist = abs(close - nearest["price"]) / (close + 1e-10) * 100
            if dist < 2.0:
                risk_flags.append("near_resistance")
                reasons.append(f"Near resistance: {nearest['price']:.2f} ({dist:.1f}% away)")
        if close > 0 and ema20 > 0:
            over = (close - ema20) / ema20 * 100
            if over > 5.0:
                risk_flags.append("extended_above_ema")
                reasons.append(f"Extended above EMA20: +{over:.1f}%")
        if indicator.high_52w and indicator.low_52w:
            if indicator.low_52w > 0:
                dist_low = (close - indicator.low_52w) / indicator.low_52w * 100
                if dist_low < 10.0:
                    w = weights.get("near_52w_low", 5)
                    score += w
                    low = indicator.low_52w
                    reasons.append(
                        f"Near 52-week low: {dist_low:.1f}% above ({close:.2f} vs {low:.2f}) (+{w})"
                    )
        # Fundamentals
        from nepse_sense.db.models import Fundamental

        fund = (
            self.db.query(Fundamental)
            .filter(Fundamental.symbol == symbol)
            .order_by(Fundamental.date.desc())
            .first()
        )
        if fund:
            w = weights.get("fundamentals_present", 5)
            score += w
            reasons.append(f"Fundamental data available (+{w})")
            if fund.score is not None:
                reasons.append(f"Fundamental quality score: {fund.score:.1f}/100")
        else:
            risk_flags.append("fundamentals_unavailable")
        # Confidence tier
        conf_tiers = self.config.get("confidence_tiers", {})
        high_min = conf_tiers.get("high_min", 70)
        medium_min = conf_tiers.get("medium_min", 40)
        if score >= high_min:
            confidence = "high"
        elif score >= medium_min:
            confidence = "medium"
        else:
            confidence = "low"
        # Category
        cats = self.config.get("categories", {})
        buy_min = cats.get("buy_candidate_min", 60)
        watch_min = cats.get("buy_watch_min", 35)
        sell_max = cats.get("sell_review_max", 25)
        if score >= buy_min and "fundamentals_unavailable" not in risk_flags:
            category = "BUY_CANDIDATE"
        elif score >= buy_min and "fundamentals_unavailable" in risk_flags:
            category = "BUY_WATCH"
        elif score >= watch_min:
            category = "BUY_WATCH"
        elif score <= sell_max:
            category = "SELL_REVIEW"
        else:
            category = "NEUTRAL"
        key_levels = {
            "nearest_support": support_zones[0]["price"] if support_zones else None,
            "nearest_resistance": resistance_zones[0]["price"] if resistance_zones else None,
            "atr": indicator.atr14,
            "invalidation": (close - (indicator.atr14 or 0) * 2) if indicator.atr14 else None,
        }
        return SignalResult(
            symbol=symbol,
            date=dt,
            category=category,
            score=round(max(0.0, min(100.0, score)), 2),
            reasons=reasons,
            risk_flags=risk_flags,
            confidence_tier=confidence,
            key_levels=key_levels,
            data_asof=canonical.date,
            sources=canonical.sources if isinstance(canonical.sources, list) else [],
        )

    def evaluate_all(self, dt: date) -> list[SignalResult]:
        symbols = self.db.query(PriceCanonical.symbol).distinct().all()
        results = []
        for (symbol,) in symbols:
            try:
                result = self.evaluate_symbol(symbol, dt)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"Failed to evaluate {symbol}: {e}")
        results.sort(key=lambda x: x.score, reverse=True)
        return results
