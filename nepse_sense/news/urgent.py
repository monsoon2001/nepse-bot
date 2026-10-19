"""Opt-in urgent alerts: high-impact news about a user's watchlist during market hours.

Per-user setting `urgent_alerts` (default OFF). Deduped per user via AlertSent.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from nepse_sense.bot.formatter import escape_html
from nepse_sense.config import settings
from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import AlertSent, User
from nepse_sense.logging import logger
from nepse_sense.news.briefing import BriefingItem, SendFn, query_items
from nepse_sense.news.impact import HIGH_IMPACT_THRESHOLD
from nepse_sense.news.ingest import ingest_news
from nepse_sense.news.windows import (
    NewsWindow,
    in_trading_hours,
    market_open_datetime,
)


@dataclass
class UrgentRun:
    status: str = "skipped"  # skipped | success | failed
    detail: str = ""
    new_items: int = 0
    delivered: int = 0
    items: list[BriefingItem] = field(default_factory=list)


def _urgent_users() -> list[User]:
    with SessionLocal() as session:
        rows = session.execute(
            select(User).where(User.is_active.is_(True))
        ).scalars()
        result = []
        for u in rows:
            s = u.settings or {}
            if s.get("urgent_alerts", False):
                result.append(u)
        return result


def _already_alerted(telegram_id: int, item: BriefingItem, day) -> bool:
    h = hashlib.sha256(f"urgent|{item.news_id}|{item.headline}".encode()).hexdigest()
    with SessionLocal() as session:
        row = session.execute(
            select(AlertSent.id).where(
                AlertSent.telegram_id == telegram_id,
                AlertSent.signal_type == "urgent_news",
                AlertSent.date == day,
                AlertSent.message_hash == h,
            )
        ).first()
    return row is not None


def _mark_alerted(telegram_id: int, item: BriefingItem, day, score: float) -> None:
    h = hashlib.sha256(f"urgent|{item.news_id}|{item.headline}".encode()).hexdigest()
    with SessionLocal() as session:
        session.add(
            AlertSent(
                telegram_id=telegram_id,
                symbol=item.symbol,
                signal_type="urgent_news",
                date=day,
                score=score,
                message_hash=h,
            )
        )
        session.commit()


def format_urgent_item(item: BriefingItem) -> str:
    sym = f" <code>{escape_html(item.symbol)}</code>" if item.symbol else ""
    lines = [f"⚡ <b>Urgent market news{sym}</b>"]
    lines.append(escape_html(item.headline))
    src = escape_html(item.source or "unknown")
    link = f' · <a href="{escape_html(item.url)}">link</a>' if item.url else ""
    lines.append(f"<i>{src} · {item.time_label}{link}</i>")
    lines.append("<i>Educational analysis, not financial advice.</i>")
    return "\n".join(lines)


async def run_urgent_news(
    send: SendFn | None = None,
    now: datetime | None = None,
    sources=None,
    feed_urls: list[str] | None = None,
    deliver: bool = True,
) -> UrgentRun:
    """Ingest during market hours; push high-impact watchlist news to opted-in users."""
    tz = ZoneInfo(settings.timezone)
    now = now.astimezone(tz) if now else datetime.now(tz)
    if not in_trading_hours(now):
        return UrgentRun(status="skipped", detail="outside market hours")

    start = market_open_datetime(now)
    try:
        report = await ingest_news(start, now, sources=sources, feed_urls=feed_urls)
    except Exception as e:
        logger.warning(f"urgent news ingest failed: {e}")
        return UrgentRun(status="failed", detail=str(e))

    if report.no_sources_enabled:
        return UrgentRun(status="skipped", detail=report.no_sources_reason or "no sources")

    window_items = query_items(NewsWindow(start=start, end=now, label="today"), limit=100)
    urgent_items = [
        it
        for it in window_items
        if it.on_watchlist and it.score >= HIGH_IMPACT_THRESHOLD
    ]
    run = UrgentRun(status="success", new_items=report.stored, items=urgent_items)
    if not urgent_items or not deliver:
        return run

    users = _urgent_users()
    if not users:
        return run
    if send is None:
        run.status = "failed"
        run.detail = "no Telegram sender configured"
        return run

    today = now.date()
    for it in urgent_items:
        text = format_urgent_item(it)
        for u in users:
            if _already_alerted(u.telegram_id, it, today):
                continue
            try:
                await send(u.telegram_id, text)
                _mark_alerted(u.telegram_id, it, today, it.score)
                run.delivered += 1
            except Exception as e:
                logger.warning(f"urgent alert send failed for {u.telegram_id}: {e}")
    return run
