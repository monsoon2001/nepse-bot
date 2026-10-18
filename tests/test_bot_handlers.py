
from nepse_sense.bot.formatter import escape_html, format_signal_message, paginate


def test_escape_html():
    assert escape_html("<script>") == "&lt;script&gt;"
    assert escape_html("a & b") == "a &amp; b"


def test_format_signal_message():
    from types import SimpleNamespace

    sig = SimpleNamespace(
        category="BUY_WATCH",
        score=45.0,
        confidence_tier="medium",
        reasons=["test reason"],
        risk_flags=["near_resistance"],
    )
    msg = format_signal_message("TEST", sig, data_asof="2024-01-01")
    assert "TEST" in msg
    assert "BUY_WATCH" in msg
    assert "test reason" in msg
    assert "near_resistance" in msg
    assert "not financial advice" in msg


def test_paginate():
    items = list(range(10))
    page1, p1, tp = paginate(items, page=1, per_page=5)
    assert len(page1) == 5
    assert p1 == 1
    assert tp == 2
    page2, p2, _ = paginate(items, page=2, per_page=5)
    assert len(page2) == 5
    assert page1[0] == 0
    assert page2[0] == 5


def test_pagination_out_of_range():
    items = list(range(3))
    page, p, tp = paginate(items, page=99, per_page=5)
    assert p <= tp
    assert len(page) <= 5
