from datetime import date, timedelta

from nepse_sense.backtest.costs import NepseCosts
from nepse_sense.backtest.engine import Backtester, BacktestResult
from nepse_sense.backtest.report import format_report
from nepse_sense.db.engine import SessionLocal, engine
from nepse_sense.db.models import Base, PriceCanonical, Signal


def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _add_prices(symbol, start, days, base=100.0):
    db = SessionLocal()
    d = start
    price = base
    for _ in range(days):
        db.add(
            PriceCanonical(
                symbol=symbol,
                date=d,
                open=price,
                high=price * 1.03,
                low=price * 0.98,
                close=price,
                volume=10000,
                sources=["test"],
                is_validated=True,
            )
        )
        price *= 1.01
        d += timedelta(days=1)
    db.commit()
    db.close()


def test_no_lookahead_entry():
    """Entry must be next day's open, never the signal day itself."""
    setup_db()
    start = date(2024, 1, 1)
    _add_prices("AAA", start, 30)
    db = SessionLocal()
    db.add(Signal(symbol="AAA", date=start, type="BUY_CANDIDATE", score=80.0))
    db.commit()
    db.close()
    bt = Backtester(holding_period=5)
    result = bt.run(start, start + timedelta(days=40), min_score=50)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_date > start
    assert trade.entry_date == start + timedelta(days=1)
    bt.db.close()


def test_costs_reduce_returns():
    setup_db()
    start = date(2024, 1, 1)
    _add_prices("BBB", start, 30)
    db = SessionLocal()
    db.add(Signal(symbol="BBB", date=start, type="BUY_CANDIDATE", score=80.0))
    db.commit()
    db.close()
    free = NepseCosts(
        broker_commission_rate=0,
        sebon_fee_rate=0,
        dp_charge=0,
        capital_gains_tax_rate=0,
        slippage_rate=0,
    )
    costly = NepseCosts(
        broker_commission_rate=0.01,
        sebon_fee_rate=0.001,
        dp_charge=50,
        capital_gains_tax_rate=0.1,
        slippage_rate=0.01,
    )
    bt1 = Backtester(costs=free, holding_period=5)
    r1 = bt1.run(start, start + timedelta(days=40), min_score=50)
    bt1.db.close()
    bt2 = Backtester(costs=costly, holding_period=5)
    r2 = bt2.run(start, start + timedelta(days=40), min_score=50)
    bt2.db.close()
    if r1.trades and r2.trades:
        assert r1.trades[0].return_pct > r2.trades[0].return_pct


def test_walk_forward_split():
    setup_db()
    start = date(2024, 1, 1)
    _add_prices("CCC", start, 60)
    db = SessionLocal()
    for i in range(0, 40, 5):
        db.add(
            Signal(
                symbol="CCC",
                date=start + timedelta(days=i),
                type="BUY_CANDIDATE",
                score=80.0,
            )
        )
    db.commit()
    db.close()
    bt = Backtester(holding_period=3)
    result = bt.run_walk_forward(start, start + timedelta(days=80), split_pct=0.6)
    assert result.in_sample_stats is not None
    assert result.out_sample_stats is not None
    bt.db.close()


def test_format_report():
    r = BacktestResult()
    r.in_sample_stats = {
        "num_trades": 5,
        "win_rate": 60.0,
        "avg_return": 1.5,
        "profit_factor": 2.0,
        "total_return": 7.5,
        "max_drawdown": 3.0,
    }
    r.buy_hold_return = 5.0
    text = format_report(r)
    assert "Backtest Report" in text
    assert "verify current" in text.lower()
