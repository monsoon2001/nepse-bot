# Signals Documentation

This documents every signal rule, weight, category, confidence tier, risk flag, and gating condition used by the NEPSE Sense signal engine.

## Scoring Model

The signal engine computes a rule-based score (0-100) using weights defined in `config/signals.yaml`. Each rule adds points (positive for bullish, negative for bearish) and produces a human-readable reason string.

## Categories

| Category | Score Range | Notes |
|----------|-------------|-------|
| BUY_CANDIDATE | score >= buy_candidate_min AND fundamentals present | Strong buy signal |
| BUY_WATCH | score >= buy_watch_min, OR score >= buy_candidate_min but fundamentals unavailable | Watch candidate, not strong enough for BUY_CANDIDATE |
| SELL_REVIEW | score <= sell_review_max | Bearish, review for potential exit |
| NEUTRAL | between sell_review_max and buy_watch_min | No clear signal |

**Critical Rule:** If fundamentals are unavailable, the signal is capped at BUY_WATCH (never BUY_CANDIDATE).

## Confidence Tiers

Based on final score:
- **high**: score >= 70
- **medium**: score >= 40
- **low**: score < 40

## Signal Rules (Bullish - add to score)

| Rule ID | Weight | Description |
|---------|--------|-------------|
| ema_trend_bullish | +15 | Price > EMA20 and EMA20 > EMA50 (bullish trend) |
| rsi_reversal_up | +12 | RSI14 crossed up from below 30 (oversold reversal) |
| macd_crossover_up | +10 | MACD line crossed above signal line (bullish momentum) |
| high_relative_volume | +8 | Relative volume > 1.5x 20-day average |
| near_support | +7 | Price within 2% of a support zone |
| near_52w_low | +5 | Price within 10% of 52-week low (value territory) |
| fundamentals_present | +5 | Fundamental data exists for this symbol |

## Signal Rules (Bearish - subtract from score)

| Rule ID | Weight | Description |
|---------|--------|-------------|
| ema_trend_bearish | -15 | Price < EMA20 and EMA20 < EMA50 (bearish trend) |
| rsi_reversal_down | -12 | RSI14 crossed down from above 70 (overbought reversal) |
| macd_crossover_down | -10 | MACD line crossed below signal line (bearish momentum) |
| near_resistance | -7 | Price within 2% of a resistance zone |
| extended_above_ema | -5 | Price more than 5% above EMA20 (overextended) |

## Risk Flags

Risk flags are warnings attached to the signal (do not affect score):

| Risk Flag | Condition |
|-----------|-----------|
| near_resistance | Price within 2% of a resistance zone |
| extended_above_ema | Price more than 5% above EMA20 |
| unadjusted_gap | Recent suspicious jump (>10%) without a matching corporate action event |
| stale_fundamentals | Fundamental data older than 365 days |
| circuit_limit_move | Daily move at or beyond NEPSE circuit limit (+/- 10%) |
| fundamentals_unavailable | No fundamental data available for this symbol |
| low_liquidity | Average turnover below configured threshold |

## Key Levels

Each signal includes key levels for trade planning:
- `nearest_support`: Nearest support zone price
- `nearest_resistance`: Nearest resistance zone price
- `atr`: 14-period Average True Range
- `invalidation`: close - (ATR * 2) — suggested invalidation level for stop-loss

## Gating Conditions (Stale/Invalid Data)

**No signal is produced if any of these conditions are true:**
1. **Critical data quality issues**: Unresolved `critical` severity issues (zero/negative prices, high < low, close outside range, etc.) exist for the symbol.
2. **Insufficient history**: Fewer than `min_bars` (default 50) valid canonical price bars.
3. **Stale data**: Latest data date is significantly behind the current expected NEPSE trading day.

When any of these gates trigger, the engine logs an exclusion reason and skips the symbol entirely. This ensures we never generate a fresh signal from stale, missing, or unvalidated data.

## Fundamental Quality Score (0-100)

Computed by `FundamentalScorer` when fundamental data is available. Transparent breakdown:
- **EPS** (up to 30 pts): Scaled by EPS value (higher = better), capped at 30.
- **P/E** (up to 25 pts): Lower P/E scores higher (value). P/E <= 25 scores well; very high P/E scores poorly.
- **P/B** (up to 20 pts): P/B between min_pb and max_pb scores full points.
- **Sector-relative P/E** (up to 15 pts): P/E at or below sector average scores full points.

If any fundamental field is missing, it contributes 0 to that component. If NO fundamental data exists at all, the score returns `None` with reason "No fundamental data available", and the symbol is capped at BUY_WATCH for signals.

## Configuration

All weights, category thresholds, and confidence tier thresholds are defined in `config/signals.yaml` and can be tuned without code changes.
