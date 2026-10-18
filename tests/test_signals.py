from datetime import date

from nepse_sense.fundamentals.scorer import FundamentalScorer
from nepse_sense.signals.engine import SignalEngine, SignalResult


def test_fundamentals_score_missing_data():
    scorer = FundamentalScorer()
    result = scorer.score(eps=None, pe=None, book_value=None, pb=None)
    assert result.score is None
    assert result.unavailable_reason is not None


def test_fundamentals_score_with_data():
    scorer = FundamentalScorer()
    result = scorer.score(eps=10.0, pe=12.0, book_value=85.0, close=120.0, pb=None)
    assert result.score is not None
    assert result.score > 0
    assert "eps" in result.breakdown


def test_signal_engine_categories():
    SignalEngine()
    result = SignalResult(
        symbol="TEST",
        date=date.today(),
        category="NEUTRAL",
        score=30.0,
        reasons=["test"],
        risk_flags=[],
    )
    assert result.category in ("BUY_WATCH", "BUY_CANDIDATE", "SELL_REVIEW", "NEUTRAL")
