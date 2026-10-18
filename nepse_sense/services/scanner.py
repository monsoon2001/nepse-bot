from __future__ import annotations

from datetime import date, datetime

from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import PriceCanonical, PriceDaily, ScanRun, Signal
from nepse_sense.logging import logger
from nepse_sense.signals.engine import SignalEngine


def latest_data_date() -> date | None:
    db = SessionLocal()
    row = db.query(PriceDaily.date).order_by(PriceDaily.date.desc()).first()
    db.close()
    return row[0] if row else None


def run_scan(target_date: date | None = None) -> dict:
    """Run the full pipeline: canonicalize -> indicators -> signals."""
    if target_date is None:
        target_date = latest_data_date()
    if target_date is None:
        logger.error("No price data available for scan")
        return {"signals": 0, "scanned": 0, "excluded": 0, "date": None}

    logger.info(f"Running scan pipeline for {target_date}")

    # Step 1: Build canonical rows from validated prices
    from nepse_sense.validation.canonical import CanonicalBuilder

    cb = CanonicalBuilder()
    cb.build_all_canonical(end=target_date)
    cb.db.close()

    # Step 2: Compute indicators
    from nepse_sense.indicators.calculator import IndicatorCalculator

    calc = IndicatorCalculator()
    calc.calculate_all(min_bars=10)
    calc.db.close()

    # Step 3: Generate signals
    engine = SignalEngine()
    results = engine.evaluate_all(target_date)

    db = SessionLocal()
    symbols_total = db.query(PriceCanonical.symbol).distinct().count()
    symbols_with_signal = {r.symbol for r in results}
    excluded = symbols_total - len(symbols_with_signal)

    # Clear prior signals for this date, store fresh
    db.query(Signal).filter(Signal.date == target_date).delete()
    for r in results:
        db.add(
            Signal(
                symbol=r.symbol,
                date=r.date,
                type=r.category,
                score=r.score,
                reasons=r.reasons,
                risk_flags=r.risk_flags,
                confidence_tier=r.confidence_tier,
                key_levels=r.key_levels,
                data_asof=r.data_asof,
                sources=r.sources,
            )
        )
    db.commit()

    db.add(
        ScanRun(
            run_type="scan",
            status="completed",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            symbols_processed=symbols_total,
            symbols_excluded=excluded,
            signals_generated=len(results),
        )
    )
    db.commit()
    db.close()
    logger.info(
        f"Scan complete: {len(results)} signals, {symbols_total} symbols, {excluded} excluded"
    )
    return {
        "signals": len(results),
        "scanned": symbols_total,
        "excluded": excluded,
        "date": target_date,
    }
