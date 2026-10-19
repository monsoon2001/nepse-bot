"""Pre-market briefing builder + delivery, and /news queries.

Briefing content (requirement: headline/source/published time/link only —
no article text, max 10 items, watchlist stocks first, impact-ranked):

    🌅 Pre-Market Briefing
    <weekday, date> · <time> NPT

    📅 Today's events & deadlines
    • ...

    📰 News <window label>
    1. Headline
       source · 17 Oct 18:32 · link

    ⚠️ explicit messages when no source is enabled / all sources failed
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import select

from nepse_sense.bot.formatter import escape_html
from nepse_sense.config import settings
from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import Event, News, NewsBriefing, User, Watchlist
from nepse_sense.logging import logger
from nepse_sense.news.impact import rank_items
from nepse_sense.news.ingest import IngestReport, ingest_news
from nepse_sense.news.windows import (
    NewsWindow,
    briefing_time,
    to_local,
    utc_naive,
    window_for_briefing,
    window_from_arg,
)

# send(chat_id, text) — injectable for tests / scheduler thread
SendFn = Callable[[int, str], Awaitable[None]]


@dataclass
class BriefingItem:
    news_id: int
    headline: str
    source: str | None
    published_at: datetime | None  # aware local
    url: str | None
    score: float
    symbol: str | None
    on_watchlist: bool

    @property
    def time_label(self) -> str:
        if not self.published_at:
            return "—"
        return self.published_at.strftime("%d %b %H:%M")


@dataclass
class EventInfo:
    symbol: str
    event_date: date
    event_type: str
    description: str | None = None

    @property
    def label(self) -> str:
        base = f"{self.symbol} — {self.event_type}"
        if self.description:
            base += f" ({self.description})"
        return base


@dataclass
class Briefing:
    window: NewsWindow
    now: datetime
    items: list[BriefingItem] = field(default_factory=list)
    events: list[EventInfo] = field(default_factory=list)
    no_sources_reason: str | None = None
    sources_failed: list[str] = field(default_factory=list)
    ingest: IngestReport | None = None

    @property
    def has_explicit_warning(self) -> bool:
        return bool(self.no_sources_reason) or bool(self.sources_failed)


# ------------------------------------------------------------------ queries


def query_items(
    window: NewsWindow, symbol: str | None = None, limit: int | None = None
) -> list[BriefingItem]:
    """Stored news inside `window` (UTC bounds), impact-ranked, watchlist first."""
    limit = limit or settings.news_max_items
    watchlist = _watchlist_symbols()
    stmt = select(News).where(
        News.published_at.is_not(None),
        News.published_at >= window.start_utc,
        News.published_at <= window.end_utc,
    )
    if symbol:
        stmt = stmt.where(News.symbol == symbol.upper())
    with SessionLocal() as session:
        rows = session.execute(stmt).scalars().all()

    items = [
        BriefingItem(
            news_id=r.id,
            headline=r.title or "",
            source=r.source,
            published_at=to_local(r.published_at) if r.published_at else None,
            url=r.url,
            score=float(r.impact_score or 0.0),
            symbol=r.symbol,
            on_watchlist=bool(r.symbol and r.symbol.upper() in watchlist),
        )
        for r in rows
    ]
    # a later-window /news must not miss newer higher-impact stories: rank fully
    return rank_items(items, max_items=limit)


def today_events(now: datetime) -> list[EventInfo]:
    """Corporate events/deadlines falling on `now`'s local date."""
    today = now.date()
    with SessionLocal() as session:
        rows = session.execute(select(Event).where(Event.date == today)).scalars().all()
    return [
        EventInfo(
            symbol=e.symbol or "—",
            event_date=e.date,
            event_type=e.event_type,
            description=e.description,
        )
        for e in rows
    ]


def _watchlist_symbols() -> set[str]:
    with SessionLocal() as session:
        rows = session.execute(select(Watchlist.symbol)).all()
    return {r[0].upper() for r in rows if r[0]}


def _active_users() -> list[User]:
    with SessionLocal() as session:
        return list(session.execute(select(User).where(User.is_active.is_(True))).scalars())


def _last_successful_cursor(kind: str = "premarket") -> datetime | None:
    with SessionLocal() as session:
        row = session.execute(
            select(NewsBriefing)
            .where(NewsBriefing.kind == kind, NewsBriefing.status == "success")
            .order_by(NewsBriefing.sent_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return row.sent_at if row else None


# ------------------------------------------------------------------ builder


def build_briefing(
    window: NewsWindow,
    now: datetime,
    *,
    ingest: IngestReport | None = None,
    max_items: int | None = None,
    no_sources_reason: str | None = None,
) -> Briefing:
    """Assemble briefing content from stored news + today's events."""
    max_items = max_items or settings.news_max_items
    b = Briefing(
        window=window,
        now=now,
        events=today_events(now),
        no_sources_reason=no_sources_reason,
        sources_failed=list(ingest.sources_failed) if ingest else [],
        ingest=ingest,
    )
    b.items = query_items(window, symbol=window.symbol, limit=max_items)
    return b


def format_briefing(b: Briefing) -> str:
    """HTML briefing text. Items: headline / source / time / link only."""
    header_line = b.now.strftime("%A, %d %b %Y")
    lines = [f"🌅 <b>{escape_html('Pre-Market Briefing')}</b>"]
    lines.append(f"<i>{escape_html(header_line)} · {b.now.strftime('%H:%M')} NPT</i>")

    # explicit no-source / failure messages (never silently omit)
    if b.no_sources_reason:
        lines.append("")
        lines.append(f"⚠️ {escape_html(b.no_sources_reason)}")
    if b.sources_failed:
        failed = "; ".join(b.sources_failed)
        lines.append("")
        lines.append(f"⚠️ <b>All news sources failed.</b> {escape_html(failed)}")
        lines.append("<i>No news items could be included.</i>")

    # events & deadlines
    lines.append("")
    lines.append("📅 <b>Today's events &amp; deadlines</b>")
    if b.events:
        for e in b.events[:10]:
            lines.append(f"  • {escape_html(e.label)}")
    else:
        lines.append("  <i>None recorded for today.</i>")

    # news items
    lines.append("")
    window_label = b.window.label
    if b.items:
        lines.append(f"📰 <b>News ({escape_html(window_label)})</b>")
        for i, it in enumerate(b.items, 1):
            mark = "★ " if it.on_watchlist else ""
            lines.append(f"{i}. {mark}{escape_html(it.headline)}")
            src = escape_html(it.source or "unknown")
            link = ""
            if it.url:
                link = f' · <a href="{escape_html(it.url)}">link</a>'
            lines.append(f"   <i>{src} · {it.time_label}{link}</i>")
        if b.ingest and b.ingest.partial_failure:
            lines.append(
                f"<i>Note: {escape_html('; '.join(b.sources_failed))} — "
                "partial results only.</i>"
            )
    else:
        if not b.no_sources_reason and not b.sources_failed:
            lines.append(f"📰 <b>News ({escape_html(window_label)})</b>")
            lines.append("  <i>No relevant news in this window.</i>")

    lines.append("")
    lines.append("<i>Educational analysis, not financial advice.</i>")
    return "\n".join(lines)


# ------------------------------------------------------------------ delivery


@dataclass
class BriefingRun:
    briefing: Briefing
    delivered_to: int = 0
    status: str = "success"  # success | failed
    detail: str = ""


def _record_cursor(b: Briefing, status: str, delivered_to: int) -> None:
    with SessionLocal() as session:
        session.add(
            NewsBriefing(
                kind="premarket",
                sent_at=datetime.utcnow(),
                status=status,
                window_start=utc_naive(b.window.start),
                item_count=len(b.items),
                event_count=len(b.events),
                delivered_to=delivered_to,
                details={"label": b.window.label, "sources_failed": b.sources_failed},
            )
        )
        session.commit()


async def run_briefing(
    send: SendFn | None = None,
    now: datetime | None = None,
    sources=None,
    feed_urls: list[str] | None = None,
    deliver: bool = True,
) -> BriefingRun:
    """Ingest → build → deliver the pre-market briefing → record the cursor.

    The cursor only advances on a *successful* run (briefing built and either
    delivered to ≥1 user or there were no recipients), so a failed run leaves
    the "since last successful briefing" window intact for the next attempt.
    """
    now = now or datetime.now(ZoneInfo(settings.timezone))
    cursor = _last_successful_cursor("premarket")
    window = window_for_briefing(now, cursor)

    ingest_report: IngestReport | None
    if sources == []:  # explicit "no sources" for tests / disabled config
        ingest_report = IngestReport(
            no_sources_enabled=True,
            no_sources_reason=(
                "No permitted news source is enabled "
                "(NEWS_FEED_URLS is empty; RSS-only, robots.txt checked)."
            ),
            window_start=window.start,
            window_end=window.end,
        )
    else:
        ingest_report = await ingest_news(
            window.start_utc, window.end_utc, sources=sources, feed_urls=feed_urls
        )

    no_reason = None
    if ingest_report.no_sources_enabled:
        no_reason = ingest_report.no_sources_reason
    elif ingest_report.all_failed:
        no_reason = None  # sources_failed message is rendered instead

    briefing = build_briefing(
        window, now, ingest=ingest_report, no_sources_reason=no_reason
    )
    text = format_briefing(briefing)

    if not deliver:
        return BriefingRun(briefing=briefing, status="success")

    run = BriefingRun(briefing=briefing)
    if send is None:
        run.status = "failed"
        run.detail = "no Telegram sender configured"
        _record_cursor(briefing, run.status, 0)
        logger.warning(f"pre-market briefing not delivered: {run.detail}")
        return run

    recipients = _active_users()
    if not recipients:
        # nothing to deliver — window still closes so it does not grow forever
        _record_cursor(briefing, "success", 0)
        run.delivered_to = 0
        run.detail = "no active recipients"
        return run

    for u in recipients:
        try:
            await send(u.telegram_id, text)
            run.delivered_to += 1
        except Exception as e:
            logger.warning(f"briefing send failed for {u.telegram_id}: {e}")

    run.status = "success" if run.delivered_to else "failed"
    if not run.delivered_to:
        run.detail = "all deliveries failed"
    _record_cursor(briefing, run.status, run.delivered_to)
    return run


# ------------------------------------------------------------------ /news


@dataclass
class NewsQuery:
    window: NewsWindow
    items: list[BriefingItem]
    total_matching: int = 0

    def page(self, page: int, per_page: int = 5) -> tuple[list[BriefingItem], int, int]:
        """Returns (items_on_page, page, total_pages)."""
        total_pages = max(1, -(-len(self.items) // per_page))
        page = max(1, min(total_pages, page))
        start = (page - 1) * per_page
        return self.items[start : start + per_page], page, total_pages


async def refresh_news(window: NewsWindow) -> IngestReport | None:
    """Best-effort ingest for a window; returns None on failure (soft-fail)."""
    try:
        return await ingest_news(window.start_utc, window.end_utc)
    except Exception as e:
        logger.warning(f"news refresh failed (showing stored news): {e}")
        return None


def run_news_query(
    arg: str | None = None,
    now: datetime | None = None,
    cursor: datetime | None = None,
    limit: int | None = None,
) -> NewsQuery:
    """Resolve a /news argument into a window + stored items (pure, no network).

    Callers should `await refresh_news(window)` first when they want fresh data.
    """
    window = window_from_arg(arg, now=now, cursor=cursor)
    total = query_items(window, symbol=window.symbol, limit=limit or 100)
    shown = rank_items(total, max_items=limit or settings.news_max_items)
    return NewsQuery(window=window, items=shown, total_matching=len(total))


async def news_query_async(
    arg: str | None = None,
    now: datetime | None = None,
    limit: int | None = None,
) -> NewsQuery:
    """Async variant for the /news command: refresh (best-effort) then query."""
    window = window_from_arg(arg, now=now)
    await refresh_news(window)
    total = query_items(window, symbol=window.symbol, limit=limit or 100)
    shown = rank_items(total, max_items=limit or settings.news_max_items)
    return NewsQuery(window=window, items=shown, total_matching=len(total))


def format_news_query(q: NewsQuery, page: int = 1, per_page: int = 5) -> str:
    lines = ["📰 <b>News</b>"]
    lines.append(f"<i>{escape_html(q.window.label)}")
    if q.window.symbol:
        lines.append(f"symbol: <code>{escape_html(q.window.symbol)}</code>")
    lines.append("</i>")
    if not q.items:
        lines.append("<i>No news items in this window.</i>")
        lines.append("")
        lines.append("<i>Educational analysis, not financial advice.</i>")
        return "\n".join(lines)

    items, page, pages = q.page(page, per_page=per_page)
    lines.append("")
    for i, it in enumerate(items, start=(page - 1) * per_page + 1):
        mark = "★ " if it.on_watchlist else ""
        lines.append(f"{i}. {mark}{escape_html(it.headline)}")
        src = escape_html(it.source or "unknown")
        link = f' · <a href="{escape_html(it.url)}">link</a>' if it.url else ""
        sym = f" · <code>{escape_html(it.symbol)}</code>" if it.symbol else ""
        lines.append(f"   <i>{src} · {it.time_label}{sym}{link}</i>")
    lines.append("")
    lines.append(f"<i>Page {page}/{pages} · {len(q.items)} item(s)</i>")
    lines.append("<i>Educational analysis, not financial advice.</i>")
    return "\n".join(lines)


def next_briefing_label(now: datetime | None = None) -> str:
    """Human label for the next briefing slot (configured trading days + time)."""
    from nepse_sense.calendar.trading_calendar import TradingCalendar

    tz = ZoneInfo(settings.timezone)
    local = now.astimezone(tz) if now else datetime.now(tz)
    t: time = briefing_time()
    cal = TradingCalendar()
    for days_ahead in range(0, 8):
        d = date.fromordinal(local.toordinal() + days_ahead)
        if cal.is_trading_day(d):
            slot = datetime.combine(d, t, tzinfo=tz)
            if slot > local:
                return slot.strftime("%a %d %b %H:%M")
    return f"{t.strftime('%H:%M')}"
