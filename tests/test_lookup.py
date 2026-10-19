"""Quick stock lookup: exact/fuzzy matching, cards, charts, unavailable states."""

from __future__ import annotations

import json
from datetime import date, timedelta
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nepse_sense.bot.lookup import (
    find_symbol,
    looks_like_ticker,
    suggest_symbols,
    symbol_status,
)
from nepse_sense.db.engine import Base, SessionLocal, engine
from nepse_sense.db.models import (
    DataQualityIssue,
    IndicatorDaily,
    PriceCanonical,
    Symbol,
)


def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed_symbol(symbol="SYN01", bars=60, end=None, critical=False):
    end = end or (date.today() - timedelta(days=1))
    db = SessionLocal()
    start = end - timedelta(days=bars - 1)
    zones = json.dumps({"support": [{"price": 90, "touches": 2}], "resistance": []})
    for i in range(bars):
        d = start + timedelta(days=i)
        px = 100.0 + i
        db.add(
            PriceCanonical(
                symbol=symbol,
                date=d,
                open=px,
                high=px + 2,
                low=px - 2,
                close=px,
                volume=10000,
                sources=["test"],
                is_validated=True,
            )
        )
        db.add(
            IndicatorDaily(
                symbol=symbol,
                date=d,
                ema20=px,
                ema50=px,
                rsi14=50.0,
                macd_line=0.1,
                macd_signal=0.05,
                atr14=2.0,
                zones=zones,
            )
        )
    db.add(Symbol(symbol=symbol, company_name=symbol))
    if critical:
        db.add(
            DataQualityIssue(
                symbol=symbol,
                date=end,
                issue_type="spike",
                severity="critical",
                description="price spike > 50%",
                resolved=False,
            )
        )
    db.commit()
    db.close()


def make_msg_update(text="syn01", user_id=123):
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    update.message = MagicMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def make_cb_update(data="chart:SYN01:6M", user_id=123, has_photo=False):
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    query = MagicMock()
    query.data = data
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.photo = [MagicMock()] if has_photo else []
    query.message.reply_photo = AsyncMock()
    query.message.reply_text = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.edit_message_media = AsyncMock()
    update.callback_query = query
    return update


# ------------------------------------------------------------------ unit


def test_find_symbol_exact_and_case_insensitive():
    setup_db()
    seed_symbol("SYN01")
    assert find_symbol("SYN01") == "SYN01"
    assert find_symbol("syn01") == "SYN01"
    assert find_symbol("Syn01") == "SYN01"
    assert find_symbol("NOPE") is None


def test_suggest_symbols_typo():
    setup_db()
    for s in ("SYN01", "SYN02", "SYN03"):
        seed_symbol(s)
    sugs = suggest_symbols("SYN1")
    assert "SYN01" in sugs


def test_looks_like_ticker():
    assert looks_like_ticker("NIFRA")
    assert looks_like_ticker("syn1")
    assert not looks_like_ticker("hi")
    assert not looks_like_ticker("thisiswaytoolong")
    assert not looks_like_ticker("")


def test_symbol_status_ok():
    setup_db()
    seed_symbol("SYN01", bars=60)
    with SessionLocal() as db:
        status, reason = symbol_status(db, "SYN01")
    assert status == "ok"
    assert reason is None


def test_symbol_status_insufficient_history():
    setup_db()
    seed_symbol("SYN01", bars=3)
    with SessionLocal() as db:
        status, reason = symbol_status(db, "SYN01")
    assert status == "unavailable"
    assert "insufficient history" in reason


def test_symbol_status_critical_validation():
    setup_db()
    seed_symbol("SYN01", bars=60, critical=True)
    with SessionLocal() as db:
        status, reason = symbol_status(db, "SYN01")
    assert status == "unavailable"
    assert "failed validation" in reason
    assert "price spike" in reason


# ------------------------------------------------------------------ handlers


@pytest.mark.asyncio
async def test_text_lookup_exact_match_shows_card():
    setup_db()
    seed_symbol("SYN01")
    update = make_msg_update(text="syn01")
    with patch("nepse_sense.bot.handlers.is_authorized", return_value=True):
        from nepse_sense.bot.handlers import text_lookup_handler

        await text_lookup_handler(update, MagicMock())
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "SYN01" in text
    assert "Last close" in text
    markup = update.message.reply_text.call_args[1]["reply_markup"]
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "chart:SYN01:6M" in callbacks


@pytest.mark.asyncio
async def test_text_lookup_typo_suggests():
    setup_db()
    for s in ("SYN01", "SYN02", "SYN03"):
        seed_symbol(s)
    update = make_msg_update(text="SYN1")
    with patch("nepse_sense.bot.handlers.is_authorized", return_value=True):
        from nepse_sense.bot.handlers import text_lookup_handler

        await text_lookup_handler(update, MagicMock())
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "No exact match" in text
    markup = update.message.reply_text.call_args[1]["reply_markup"]
    buttons = [b.text for row in markup.inline_keyboard for b in row]
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert any("Did you mean SYN01" in t for t in buttons)
    assert "pick:SYN01" in callbacks


@pytest.mark.asyncio
async def test_text_lookup_unknown_word_nudges_help():
    setup_db()
    update = make_msg_update(text="hello")
    with patch("nepse_sense.bot.handlers.is_authorized", return_value=True):
        from nepse_sense.bot.handlers import text_lookup_handler

        await text_lookup_handler(update, MagicMock())
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "I work with commands" in text


@pytest.mark.asyncio
async def test_unknown_command_treated_as_lookup():
    setup_db()
    seed_symbol("NIFRA")
    update = make_msg_update(text="/nifra")
    with patch("nepse_sense.bot.handlers.is_authorized", return_value=True):
        from nepse_sense.bot.handlers import unknown_command_handler

        await unknown_command_handler(update, MagicMock())
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "NIFRA" in text
    assert "Last close" in text


@pytest.mark.asyncio
async def test_chart_callback_sends_photo():
    setup_db()
    seed_symbol("SYN01")
    update = make_cb_update(data="chart:SYN01:6M")
    fake = (BytesIO(b"png-bytes"), date.today())
    with patch("nepse_sense.bot.handlers.is_authorized", return_value=True), patch(
        "nepse_sense.bot.chart.render_chart", return_value=fake
    ) as mock_render:
        from nepse_sense.bot.handlers import stock_callback

        await stock_callback(update, MagicMock())
    mock_render.assert_called_once()
    update.callback_query.message.reply_photo.assert_called_once()
    markup = update.callback_query.message.reply_photo.call_args[1]["reply_markup"]
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "chart:SYN01:3M" in callbacks
    assert "chart:SYN01:1Y" in callbacks
    assert "card:SYN01" in callbacks


@pytest.mark.asyncio
async def test_chart_timeframe_edits_photo_in_place():
    setup_db()
    seed_symbol("SYN01")
    update = make_cb_update(data="chart:SYN01:3M", has_photo=True)
    fake = (BytesIO(b"png-bytes"), date.today())
    with patch("nepse_sense.bot.handlers.is_authorized", return_value=True), patch(
        "nepse_sense.bot.chart.render_chart", return_value=fake
    ) as mock_render:
        from nepse_sense.bot.handlers import stock_callback

        await stock_callback(update, MagicMock())
    days = mock_render.call_args[0][1]
    assert days == 90  # 3M
    update.callback_query.edit_message_media.assert_called_once()
    update.callback_query.message.reply_photo.assert_not_called()


@pytest.mark.asyncio
async def test_excluded_symbol_unavailable_no_chart_button():
    setup_db()
    seed_symbol("SYN01", bars=60, critical=True)
    update = make_msg_update(text="SYN01")
    with patch("nepse_sense.bot.handlers.is_authorized", return_value=True):
        from nepse_sense.bot.handlers import text_lookup_handler

        await text_lookup_handler(update, MagicMock())
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Unavailable" in text
    assert "failed validation" in text
    markup = update.message.reply_text.call_args[1]["reply_markup"]
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert not any(c.startswith("chart:") for c in callbacks)


@pytest.mark.asyncio
async def test_alert_toggle_persists_mute():
    setup_db()
    seed_symbol("SYN01")
    update = make_cb_update(data="alert:SYN01")
    with patch("nepse_sense.bot.handlers.is_authorized", return_value=True):
        from nepse_sense.bot.handlers import stock_callback

        await stock_callback(update, MagicMock())
    with SessionLocal() as db:
        from nepse_sense.db.models import User

        user = db.query(User).filter(User.telegram_id == 123).first()
        assert user is not None
        assert "SYN01" in (user.settings or {}).get("muted_symbols", [])
    # answer() is called once as a generic ack, then again with the toast
    assert update.callback_query.answer.call_args[0][0] == "SYN01 alerts off 🔕"
