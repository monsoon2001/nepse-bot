"""Bridge between APScheduler threads and the bot's asyncio event loop."""

from __future__ import annotations

import asyncio
from typing import Any

from nepse_sense.logging import logger

MAIN_LOOP: asyncio.AbstractEventLoop | None = None
BOT: Any = None


def bind_bot(bot: Any, loop: asyncio.AbstractEventLoop) -> None:
    global MAIN_LOOP, BOT
    MAIN_LOOP = loop
    BOT = bot
    logger.info("Telegram bot bound to scheduler runtime bridge")


def unbind() -> None:
    global MAIN_LOOP, BOT
    MAIN_LOOP = None
    BOT = None


def send_text_sync(chat_id: int, text: str) -> bool:
    """Send an HTML message from a scheduler thread. Returns False if unbound."""
    if MAIN_LOOP is None or BOT is None:
        logger.warning("Telegram bot not bound — message not sent")
        return False
    coro = BOT.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    try:
        fut = asyncio.run_coroutine_threadsafe(coro, MAIN_LOOP)
        fut.result(timeout=30)
        return True
    except Exception as e:
        logger.warning(f"Scheduler send failed for chat {chat_id}: {e}")
        return False


async def send_text_async(chat_id: int, text: str) -> None:
    """Async sender used by briefing/urgent helpers (raises on failure)."""
    if BOT is None:
        raise RuntimeError("Telegram bot not bound")
    await BOT.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
