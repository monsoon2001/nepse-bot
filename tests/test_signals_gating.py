from datetime import date

from nepse_sense.db.engine import SessionLocal, engine
from nepse_sense.db.models import Base, DataQualityIssue, PriceCanonical
from nepse_sense.signals.engine import SignalEngine


def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_stale_data_gating():
    setup_db()
    db = SessionLocal()
    # PriceCanonical from 30 days ago - stale
    stale_date = date.today().toordinal() - 30

    dt = date.fromordinal(stale_date)
    pc = PriceCanonical(symbol="TEST", date=dt, close=100.0, sources=["test"], is_validated=True)
    db.add(pc)
    db.commit()
    engine_inst = SignalEngine()
    # Should be excluded due to insufficient history (min_bars=50)
    result = engine_inst.evaluate_symbol("TEST", dt)
    assert result is None
    db.close()


def test_critical_issue_exclusion():
    setup_db()
    db = SessionLocal()
    dt = date.today()
    pc = PriceCanonical(symbol="TEST", date=dt, close=100.0, sources=["test"], is_validated=True)
    issue = DataQualityIssue(
        symbol="TEST",
        date=dt,
        issue_type="zero_or_negative_close",
        severity="critical",
        resolved=False,
    )
    db.add_all([pc, issue])
    db.commit()
    engine_inst = SignalEngine()
    result = engine_inst.evaluate_symbol("TEST", dt)
    assert result is None
    db.close()
