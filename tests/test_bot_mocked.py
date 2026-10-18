from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nepse_sense.bot.handlers import brokers_command, help_command, start_command, top_command


def make_update(user_id=123):
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    update.message = AsyncMock()
    return update


def make_context():
    context = MagicMock()
    context.args = []
    return context


@pytest.mark.asyncio
async def test_start_unauthorized():
    update = make_update(user_id=999)
    context = make_context()
    with patch("nepse_sense.bot.handlers.is_authorized", return_value=False):
        await start_command(update, context)
    update.message.reply_text.assert_called_once()
    assert "Unauthorized" in update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_brokers_command():
    update = make_update(user_id=123)
    context = make_context()
    with patch("nepse_sense.bot.handlers.is_authorized", return_value=True):
        await brokers_command(update, context)
    update.message.reply_text.assert_called_once()
    assert "unavailable" in update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_help_command():
    update = make_update(user_id=123)
    context = make_context()
    with patch("nepse_sense.bot.handlers.is_authorized", return_value=True):
        await help_command(update, context)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "stock" in text.lower()


@pytest.mark.asyncio
async def test_top_command_empty():
    update = make_update(user_id=123)
    context = make_context()
    with patch("nepse_sense.bot.handlers.is_authorized", return_value=True), \
         patch("nepse_sense.bot.handlers.SessionLocal") as mock_db:
        mock_session = MagicMock()
        query_mock = mock_session.query.return_value
        query_mock.order_by.return_value.limit.return_value.all.return_value = []
        mock_db.return_value = mock_session
        await top_command(update, context)
    update.message.reply_text.assert_called_once()
    assert "No signals" in update.message.reply_text.call_args[0][0]
