from datetime import date, timedelta

from nepse_sense.db.engine import SessionLocal, engine
from nepse_sense.db.models import Base, PriceCanonical
from nepse_sense.jobs.digest import (
    build_digest_message,
    build_no_signals_message,
    dedupe_alert,
)


def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_dedupe_alert_new():
    setup_db()
    dt = date.today()
    result = dedupe_alert(1, "TEST", "BUY_WATCH", dt, 50.0)
    assert result is True


def test_dedupe_alert_duplicate():
    setup_db()
    dt = date.today()
    first = dedupe_alert(1, "TEST", "BUY_WATCH", dt, 50.0)
    second = dedupe_alert(1, "TEST", "BUY_WATCH", dt, 50.0)
    assert first is True
    assert second is False


def test_dedupe_alert_material_change_sends():
    setup_db()
    dt = date.today()
    dedupe_alert(1, "TEST", "BUY_WATCH", dt, 50.0)
    # Score changed by > 10 -> should send
    result = dedupe_alert(1, "TEST", "BUY_WATCH", dt, 75.0)
    assert result is True


def test_dedupe_alert_different_day_sends():
    setup_db()
    dt1 = date.today() - timedelta(days=3)
    dt2 = date.today()
    dedupe_alert(1, "TEST", "BUY_WATCH", dt1, 50.0)
    result = dedupe_alert(1, "TEST", "BUY_WATCH", dt2, 50.0)
    assert result is True


def test_stale_data_no_digest():
    setup_db()
    db = SessionLocal()
    old_date = date.today() - timedelta(days=30)
    db.add(
        PriceCanonical(
            symbol="TEST", date=old_date, close=100.0, sources=["test"], is_validated=True
        )
    )
    db.commit()
    db.close()
    result = build_digest_message()
    assert result is None


def test_no_signals_message():
    msg = build_no_signals_message("data stale")
    assert "No signals today" in msg
    assert "data stale" in msg


def test_digest_with_fresh_data_and_no_signals():
    setup_db()
    db = SessionLocal()
    today = date.today()
    db.add(
        PriceCanonical(
            symbol="TEST", date=today, close=100.0, sources=["test"], is_validated=True
        )
    )
    db.commit()
    db.close()
    # Fresh data but no signals stored -> returns None (no signals)
    result = build_digest_message()
    assert result is None


def test_build_scheduler():
    from nepse_sense.jobs.scheduler import build_scheduler

    scheduler = build_scheduler()
    jobs = scheduler.get_jobs()
    job_ids = [j.id for j in jobs]
    assert "ingest" in job_ids
    assert "validate" in job_ids
    assert "signals_digest" in job_ids
    assert "weekly_backfill" in job_ids
    assert "health_ping" in job_ids
