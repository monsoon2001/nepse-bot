from datetime import date

from nepse_sense.db.engine import SessionLocal, engine
from nepse_sense.db.models import Base, DataQualityIssue, PriceDaily
from nepse_sense.validation.canonical import CanonicalBuilder
from nepse_sense.validation.validators import DataValidator


def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_suspicious_jump_detection():
    setup_db()
    db = SessionLocal()
    p1 = PriceDaily(symbol="TEST", date=date(2024, 1, 1), source="s1", close=100.0)
    db.add(p1)
    p2 = PriceDaily(symbol="TEST", date=date(2024, 1, 2), source="s1", close=115.0)
    db.add(p2)
    db.commit()
    validator = DataValidator()
    issues = validator.validate_price_row(p2)
    assert any(i.issue_type == "suspicious_jump_gt10pct" for i in issues)
    db.close()


def test_cross_source_comparison():
    setup_db()
    db = SessionLocal()
    p1 = PriceDaily(symbol="TEST", date=date(2024, 1, 1), source="primary", close=100.0)
    p2 = PriceDaily(symbol="TEST", date=date(2024, 1, 1), source="secondary", close=101.5)
    db.add_all([p1, p2])
    db.commit()
    validator = DataValidator(price_tolerance_pct=1.0)
    validator.validate_cross_source("TEST", date(2024, 1, 1))
    issues = db.query(DataQualityIssue).all()
    assert len(issues) > 0
    db.close()


def test_canonical_excludes_critical_issues():
    setup_db()
    db = SessionLocal()
    p = PriceDaily(symbol="TEST", date=date(2024, 1, 1), source="s1", close=0.0)
    db.add(p)
    issue = DataQualityIssue(
        symbol="TEST",
        date=date(2024, 1, 1),
        issue_type="zero_or_negative_close",
        severity="critical",
        resolved=False,
    )
    db.add(issue)
    db.commit()
    builder = CanonicalBuilder()
    canon = builder.build_canonical_for_symbol_date("TEST", date(2024, 1, 1))
    assert canon is None
    db.close()
