"""Fetch news from enabled sources, dedupe across sources, persist to DB."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import select

from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import News, Watchlist
from nepse_sense.logging import logger
from nepse_sense.news.dedupe import headline_key, normalize_headline
from nepse_sense.news.impact import score_news_item
from nepse_sense.news.sources import (
    NewsSource,
    get_enabled_news_sources,
    no_sources_enabled_reason,
)
from nepse_sense.news.windows import utc_naive


@dataclass
class IngestReport:
    no_sources_enabled: bool = False
    no_sources_reason: str | None = None
    sources_ok: list[str] = field(default_factory=list)
    sources_failed: list[str] = field(default_factory=list)
    fetched: int = 0
    stored: int = 0
    deduped: int = 0
    irrelevant: int = 0
    window_start: datetime | None = None
    window_end: datetime | None = None

    @property
    def all_failed(self) -> bool:
        return bool(self.sources_failed) and not self.sources_ok

    @property
    def partial_failure(self) -> bool:
        return bool(self.sources_failed) and bool(self.sources_ok)


def _load_context(session) -> tuple[list[str], list[str], dict[str, list[date]]]:
    from nepse_sense.db.models import Event, Symbol

    known = [
        row[0]
        for row in session.execute(select(Symbol.symbol).distinct()).all()
        if row[0]
    ]
    known += [
        row[0] for row in session.execute(select(News.symbol).distinct()).all() if row[0]
    ]
    wl_rows = session.execute(select(Watchlist.symbol)).all()
    watchlist = [r[0] for r in wl_rows]

    events: dict[str, list[date]] = {}
    ev_rows = session.execute(
        select(Event.symbol, Event.date).where(Event.symbol.is_not(None))
    ).all()
    for sym, ev_date in ev_rows:
        if sym and ev_date:
            events.setdefault(sym.upper(), []).append(ev_date)
    # watchlist symbols are always known symbols for matching purposes
    known = sorted(set(known) | set(w.upper() for w in watchlist))
    return known, watchlist, events


async def ingest_news(
    since: datetime,
    until: datetime | None = None,
    sources: list[NewsSource] | None = None,
    feed_urls: list[str] | None = None,
) -> IngestReport:
    """Fetch, dedupe and store news items published in [since, until].

    `sources` is injectable for tests; by default it is derived from
    NEWS_FEED_URLS after a robots.txt permission check.
    """
    if sources is None:
        reason = no_sources_enabled_reason(feed_urls)
        if reason:
            return IngestReport(
                no_sources_enabled=True,
                no_sources_reason=reason,
                window_start=since,
                window_end=until,
            )
        sources = get_enabled_news_sources(feed_urls)
        if not sources:
            return IngestReport(
                no_sources_enabled=True,
                no_sources_reason=(
                    "No permitted news source is enabled "
                    "(all candidates were disallowed by robots.txt or invalid)."
                ),
                window_start=since,
                window_end=until,
            )
    else:
        if not sources:
            return IngestReport(no_sources_enabled=True, no_sources_reason="no sources given")

    # normalize bounds to aware UTC so sources can compare against aware datetimes
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    else:
        since = since.astimezone(UTC)
    if until is not None:
        until = until.replace(tzinfo=UTC) if until.tzinfo is None else until.astimezone(UTC)

    report = IngestReport(window_start=since, window_end=until)
    ref_until = until or datetime.max.replace(tzinfo=UTC)

    # per-source fetch; a failure never aborts the whole ingest
    all_items = []
    for src in sources:
        try:
            items = await src.fetch(since, ref_until)
            all_items.extend(items)
            report.sources_ok.append(src.name)
        except Exception as e:
            logger.warning(f"news source {src.name} failed: {e}")
            report.sources_failed.append(f"{src.name}: {e}")

    if report.all_failed:
        return report

    report.fetched = len(all_items)
    known, watchlist, events_by_symbol = _load_session_context()
    today = since.date()

    session = SessionLocal()
    try:
        seen: dict[str, News] = {}  # in-batch dedupe (autoflush is off)
        for item in all_items:
            if not normalize_headline(item.headline):
                report.irrelevant += 1
                continue
            pub_date = item.published_at.astimezone(UTC).date()
            key = headline_key(item.headline, pub_date)
            if key in seen:
                # same story already added in this batch from another source
                row = seen[key]
                alt = list(row.alt_sources or [])
                if item.source and item.source != row.source and item.source not in alt:
                    alt.append(item.source)
                    row.alt_sources = alt
                report.deduped += 1
                continue
            existing = session.execute(
                select(News).where(News.headline_key == key)
            ).scalar_one_or_none()
            if existing is not None:
                # cross-source dedupe: record the extra source, don't re-store
                alt = list(existing.alt_sources or [])
                if item.source and item.source != existing.source and item.source not in alt:
                    alt.append(item.source)
                    existing.alt_sources = alt
                report.deduped += 1
                continue

            impact = score_news_item(
                item.headline,
                known_symbols=known,
                watchlist_symbols=watchlist,
                events_by_symbol=events_by_symbol,
                today=today,
            )
            if not impact.is_relevant:
                report.irrelevant += 1
                continue

            row = News(
                symbol=impact.symbol,
                date=pub_date,
                title=item.headline,
                content=None,  # headline + link only; no article text stored
                source=item.source,
                impact_score=impact.score,
                url=item.url,
                published_at=utc_naive(item.published_at),
                headline_key=key,
                alt_sources=[],
            )
            session.add(row)
            seen[key] = row
            report.stored += 1
        session.commit()
    finally:
        session.close()

    return report


def _load_session_context() -> tuple[list[str], list[str], dict[str, list[date]]]:
    session = SessionLocal()
    try:
        return _load_context(session)
    finally:
        session.close()
