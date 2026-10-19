import random
from datetime import date, timedelta

from nepse_sense.clock import MarketClock
from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import Fundamental, IndicatorDaily, PriceCanonical


def seed_demo_data(num_days: int = 60, num_symbols: int = 3):
    """Seed synthetic data so everything works with no network.

    Bars are placed on configured trading days only (MarketClock), so demo data
    is consistent with TRADING_DAYS and does not trip the calendar-mismatch
    warning in /status or doctor.
    """
    clock = MarketClock()
    db = SessionLocal()
    symbols = [f"SYN{i:02d}" for i in range(1, num_symbols + 1)]
    # Clear prior demo rows so re-seeding is idempotent (no unique-constraint
    # conflicts, no stale weekend rows from an older calendar).
    db.query(PriceCanonical).filter(PriceCanonical.symbol.in_(symbols)).delete(
        synchronize_session=False
    )
    db.query(IndicatorDaily).filter(IndicatorDaily.symbol.in_(symbols)).delete(
        synchronize_session=False
    )
    db.query(Fundamental).filter(Fundamental.symbol.in_(symbols)).delete(
        synchronize_session=False
    )
    db.commit()
    start_date = date.today() - timedelta(days=num_days + 50)
    bars = num_days + 50
    for symbol in symbols:
        price = random.uniform(100, 500)
        dt = start_date
        produced = 0
        while produced < bars:
            if not clock.is_trading_day(dt):
                dt += timedelta(days=1)
                continue
            change = random.uniform(-0.03, 0.03)
            price = price * (1 + change)
            high = price * (1 + random.uniform(0, 0.02))
            low = price * (1 - random.uniform(0, 0.02))
            volume = random.uniform(10000, 50000)
            pc = PriceCanonical(
                symbol=symbol,
                date=dt,
                open=price,
                high=high,
                low=low,
                close=price,
                volume=volume,
                sources=["demo"],
                is_validated=True,
            )
            db.add(pc)
            ind = IndicatorDaily(
                symbol=symbol,
                date=dt,
                ema20=price,
                ema50=price,
                rsi14=random.uniform(30, 70),
                macd_line=random.uniform(-1, 1),
                macd_signal=random.uniform(-1, 1),
                atr14=price * 0.02,
                rel_volume=random.uniform(0.5, 2.0),
            )
            db.add(ind)
            produced += 1
            dt += timedelta(days=1)
        fund = Fundamental(
            symbol=symbol,
            date=date.today() - timedelta(days=30),
            eps=random.uniform(5, 20),
            pe=random.uniform(8, 25),
            book_value=random.uniform(50, 150),
        )
        db.add(fund)
    try:
        db.commit()
    except Exception:
        db.rollback()
    db.close()
    return symbols
