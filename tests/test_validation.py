from datetime import date

from nepse_sense.calendar.trading_calendar import TradingCalendar
from nepse_sense.db.engine import SessionLocal, engine
from nepse_sense.db.models import Base, PriceDaily
from nepse_sense.validation.validators import DataValidator


def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_trading_calendar():
    cal = TradingCalendar()
    # Nepali calendar trading days: Sun-Thu
    assert cal.is_trading_day(date(2024, 1, 1))  # Could be Mon or other
    # Just check structure
    assert hasattr(cal, "is_holiday")


def test_validate_zero_price():
    setup_db()
    db = SessionLocal()
    price = PriceDaily(
        symbol="TEST",
        date=date(2024, 1, 1),
        source="test",
        close=0.0,
    )
    db.add(price)
    db.commit()
    validator = DataValidator()
    issues = validator.validate_price_row(price)
    # Should detect zero close
    assert any(i.issue_type == "zero_or_negative_close" for i in issues)
    db.close()


def test_validate_high_low_mismatch():
    setup_db()
    db = SessionLocal()
    price = PriceDaily(
        symbol="TEST",
        date=date(2024, 1, 2),
        source="test",
        high=100.0,
        low=110.0,
        close=105.0,
    )
    db.add(price)
    db.commit()
    validator = DataValidator()
    issues = validator.validate_price_row(price)
    assert any(i.issue_type == "high_less_than_low" for i in issues)
    db.close()


def test_validate_close_outside_range():
    setup_db()
    db = SessionLocal()
    price = PriceDaily(
        symbol="TEST",
        date=date(2024, 1, 3),
        source="test",
        high=100.0,
        low=90.0,
        close=110.0,
    )
    db.add(price)
    db.commit()
    validator = DataValidator()
    issues = validator.validate_price_row(price)
    assert any(i.issue_type == "close_outside_range" for i in issues)
    db.close()
