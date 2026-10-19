"""News feature tests: windows (Thu→Sun gap), dedupe, source-down, briefing."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from nepse_sense.db.engine import SessionLocal, engine
from nepse_sense.db.models import Base, News, NewsBriefing, User, Watchlist
from nepse_sense.news.briefing import (
    build_briefing,
    format_briefing,
    format_news_query,
    run_briefing,
    run_news_query,
)
from nepse_sense.news.dedupe import headline_key, normalize_headline
from nepse_sense.news.impact import rank_items, score_news_item
from nepse_sense.news.ingest import ingest_news
from nepse_sense.news.sources import FetchedItem, NewsSource
from nepse_sense.news.urgent import run_urgent_news
from nepse_sense.news.windows import (
    since_last_close,
    window_from_arg,
)

NPT = ZoneInfo("Asia/Kathmandu")


def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


class FakeSource(NewsSource):
    def __init__(self, name="fake", items=None, fail=False):
        self.name = name
        self.items = items or []
        self.fail = fail

    async def fetch(self, since, until=None):
        if self.fail:
            raise RuntimeError(f"{self.name}: connection refused")
        end = until or datetime.max.replace(tzinfo=NPT)
        return [i for i in self.items if since <= i.published_at <= end]


def item(headline, day, hour, minute=0, source="fake", url="https://x.test/a"):
    return FetchedItem(
        headline=headline,
        url=url,
        source=source,
        published_at=datetime(day.year, day.month, day.day, hour, minute, tzinfo=NPT),
    )


# ---------------------------------------------------------------- windows


def test_window_weekend_looks_back_to_friday():
    """Sat→Sun weekend gap: a weekend morning's window starts at Friday's close.

    Default TRADING_DAYS is Mon-Fri, so the weekend is Sat+Sun and the last
    close before Sunday is Friday 15:00.
    """
    sunday = datetime(2026, 10, 18, 10, 0, tzinfo=NPT)  # Sunday 10:00 NPT
    start = since_last_close(sunday)
    assert start == datetime(2026, 10, 16, 15, 0, tzinfo=NPT)  # Friday 15:00
    assert start.isoweekday() == 5  # Friday

    # a Friday-after-close story is inside the Sunday window; Friday-morning is not
    friday_after_close = datetime(2026, 10, 16, 16, 0, tzinfo=NPT)
    friday_morning = datetime(2026, 10, 16, 10, 0, tzinfo=NPT)
    assert friday_after_close > start
    assert friday_morning < start


def test_window_monday_after_friday_close():
    """Monday pre-open still shows Friday's close (Sunday never closed)."""
    monday = datetime(2026, 10, 19, 9, 0, tzinfo=NPT)  # Monday 09:00, pre-open
    start = since_last_close(monday)
    assert start == datetime(2026, 10, 16, 15, 0, tzinfo=NPT)  # Friday 15:00
    assert start.isoweekday() == 5


def test_window_arg_clamps_n_to_seven():
    w = window_from_arg("3", now=datetime(2026, 10, 18, 10, 0, tzinfo=NPT))
    assert w.label == "last 3 days"
    assert w.symbol is None

    w_big = window_from_arg("30", now=datetime(2026, 10, 18, 10, 0, tzinfo=NPT))
    assert "capped from 30" in w_big.label
    assert w_big.end - w_big.start <= timedelta(days=7)


def test_window_arg_symbol():
    w = window_from_arg("nifra", now=datetime(2026, 10, 18, 10, 0, tzinfo=NPT))
    assert w.symbol == "NIFRA"
    assert "last market close" in w.label


# ---------------------------------------------------------------- dedupe


def test_normalize_headline_ignores_case_and_punctuation():
    a = normalize_headline("NEPSE: Index Rises 1.2%!")
    b = normalize_headline("nepse index rises 1 2")
    assert a == b


def test_normalize_headline_keeps_devanagari():
    """Regression: Devanagari is U+0900–U+097F (not the Bengali block)."""
    t = "राष्ट्र बैंक प्रतिवेदन : स्वेच्छिकभन्दा बाध्यकारी मर्जर सफल"
    assert normalize_headline(t) != ""
    assert "राष्ट्र बैंक" in normalize_headline(t)
    # punctuation stripped, words kept
    assert ":" not in normalize_headline(t)


def test_headline_key_stable_same_day():
    d = date(2026, 10, 15)
    a = headline_key("NEPSE index rises", d)
    b = headline_key("  Nepse Index Rises ", d)
    assert a == b
    assert a != headline_key("NEPSE index rises", date(2026, 10, 16))


async def test_dedupe_across_sources():
    """Same story from two sources → one row, second source recorded."""
    setup_db()
    day = date(2026, 10, 15)
    src_a = FakeSource(
        "source-a",
        [item("NEPSE: Index Rises 1.2% Amid Buying", day, 12, source="source-a")],
    )
    src_b = FakeSource(
        "source-b",
        [item("nepse index rises 1 2 amid buying", day, 13, source="source-b")],
    )
    report = await ingest_news(
        datetime(2026, 10, 15, 0, 0, tzinfo=NPT),
        datetime(2026, 10, 16, 0, 0, tzinfo=NPT),
        sources=[src_a, src_b],
    )
    assert report.stored == 1
    assert report.deduped == 1
    with SessionLocal() as session:
        rows = session.query(News).all()
        assert len(rows) == 1
        assert rows[0].alt_sources == ["source-b"]
        assert rows[0].url is not None


# ---------------------------------------------------------------- impact


def test_watchlist_stock_ranks_first():
    items = [
        type("I", (), {"score": 80, "on_watchlist": False})(),
        type("I", (), {"score": 30, "on_watchlist": True})(),
        type("I", (), {"score": 95, "on_watchlist": False})(),
    ]
    ranked = rank_items(items, max_items=2)
    assert ranked[0].on_watchlist is True
    assert ranked[1].score == 95


def test_impact_score_watchlist_and_keywords():
    r = score_news_item(
        "NIFRA declares dividend; NEPSE closes higher",
        known_symbols=["NIFRA"],
        watchlist_symbols=["NIFRA"],
    )
    assert r.symbol == "NIFRA"
    assert r.on_watchlist is True
    assert r.score >= 60  # high impact
    assert r.is_relevant


def test_irrelevant_headline_scores_zero():
    r = score_news_item("Local football team wins friendly match")
    assert r.score <= 5.0  # only the small source weight
    assert not r.on_watchlist


# ---------------------------------------------------------------- source-down


async def test_no_sources_enabled_message():
    """Explicit message when no permitted source is configured."""
    setup_db()
    run = await run_briefing(send=None, now=datetime(2026, 10, 18, 9, 55, tzinfo=NPT), sources=[])
    text = format_briefing(run.briefing)
    assert "No permitted news source is enabled" in text


async def test_all_sources_failed_message():
    setup_db()
    failing = FakeSource("onlinekhabar.com", fail=True)
    run = await run_briefing(
        send=None,
        now=datetime(2026, 10, 18, 9, 55, tzinfo=NPT),
        sources=[failing],
    )
    text = format_briefing(run.briefing)
    assert "All news sources failed" in text
    assert "connection refused" in text
    # a failed run must not advance the briefing cursor
    with SessionLocal() as session:
        rows = session.query(NewsBriefing).all()
        assert all(r.status != "success" for r in rows)


async def test_partial_failure_shows_note_and_items():
    setup_db()
    day = date(2026, 10, 18)
    ok = FakeSource("ok-source", [item("NEPSE up as banks gain", day, 8, source="ok")])
    down = FakeSource("down-source", fail=True)
    run = await run_briefing(
        send=None,
        now=datetime(2026, 10, 18, 9, 55, tzinfo=NPT),
        sources=[ok, down],
        deliver=False,
    )
    text = format_briefing(run.briefing)
    assert "NEPSE up as banks gain" in text
    assert "down-source" in text  # failure is surfaced, not hidden


# ---------------------------------------------------------------- briefing


async def test_briefing_delivery_advances_cursor():
    setup_db()
    day = date(2026, 10, 18)
    src = FakeSource(
        "fake",
        [item("NEPSE: banks lead the rally", day, 7, source="fake")],
    )
    sent = []

    async def fake_send(chat_id, text):
        sent.append((chat_id, text))

    with SessionLocal() as session:
        session.add(User(telegram_id=111, settings={}, is_active=True))
        session.commit()

    run = await run_briefing(
        send=fake_send, now=datetime(2026, 10, 18, 9, 55, tzinfo=NPT), sources=[src]
    )
    assert run.status == "success"
    assert run.delivered_to == 1
    assert len(sent) == 1
    assert "Pre-Market Briefing" in sent[0][1]
    assert "banks lead the rally" in sent[0][1]
    # item text: headline + source + time + link only, no article body
    assert "link" in sent[0][1]

    with SessionLocal() as session:
        cursor = (
            session.query(NewsBriefing)
            .filter(NewsBriefing.status == "success")
            .first()
        )
        assert cursor is not None
        assert cursor.delivered_to == 1


async def test_news_query_symbol_filter_and_window():
    setup_db()
    day = date(2026, 10, 18)
    with SessionLocal() as session:
        from nepse_sense.db.models import Symbol

        session.add(Symbol(symbol="NIFRA"))
        session.commit()
    src = FakeSource(
        "fake",
        [
            item("NIFRA bonus share, record date set", day, 7, source="fake"),
            item("NEPSE index up 15 points", day, 8, source="fake"),
        ],
    )
    await ingest_news(
        datetime(2026, 10, 18, 0, 0, tzinfo=NPT),
        datetime(2026, 10, 18, 23, 59, tzinfo=NPT),
        sources=[src],
    )
    q_all = run_news_query("1", now=datetime(2026, 10, 18, 10, 0, tzinfo=NPT))
    assert len(q_all.items) == 2
    q_sym = run_news_query("NIFRA", now=datetime(2026, 10, 18, 10, 0, tzinfo=NPT))
    assert len(q_sym.items) == 1
    assert q_sym.items[0].symbol == "NIFRA"
    text = format_news_query(q_sym)
    assert "NIFRA bonus share" in text
    assert "Page 1/1" in text


def test_news_query_empty_state():
    setup_db()
    q = run_news_query(None, now=datetime(2026, 10, 18, 10, 0, tzinfo=NPT))
    text = format_news_query(q)
    assert "No news items in this window." in text


# ---------------------------------------------------------------- urgent


async def test_urgent_alerts_default_off_and_market_hours():
    setup_db()
    # Monday 2026-10-19 is a trading day under the default Mon-Fri calendar
    day = date(2026, 10, 19)
    with SessionLocal() as session:
        session.add(User(telegram_id=222, settings={}, is_active=True))  # no urgent flag
        session.add(
            User(telegram_id=333, settings={"urgent_alerts": True}, is_active=True)
        )
        session.add(Watchlist(telegram_id=333, symbol="NIFRA"))
        session.commit()

    src = FakeSource(
        "fake",
        [item("NIFRA circuit locked after dividend news", day, 11, 30, source="fake")],
    )
    sent = []

    async def fake_send(chat_id, text):
        sent.append(chat_id)

    # outside market hours (after close) → skipped
    run_off = await run_urgent_news(
        send=fake_send,
        now=datetime(2026, 10, 19, 16, 0, tzinfo=NPT),
        sources=[src],
    )
    assert run_off.status == "skipped"

    # inside market hours, only the opted-in user is notified
    run_on = await run_urgent_news(
        send=fake_send,
        now=datetime(2026, 10, 19, 11, 45, tzinfo=NPT),
        sources=[src],
    )
    assert run_on.status == "success"
    assert sent == [333]

    # second run does not re-alert the same item (AlertSent dedupe)
    run_again = await run_urgent_news(
        send=fake_send,
        now=datetime(2026, 10, 19, 12, 0, tzinfo=NPT),
        sources=[src],
    )
    assert run_again.delivered == 0
    assert sent == [333]


# ---------------------------------------------------------------- build


def test_build_briefing_items_are_ranked_and_capped():
    setup_db()
    now = datetime(2026, 10, 18, 9, 55, tzinfo=NPT)
    with SessionLocal() as session:
        # stored as naive UTC; keep everything strictly before `now` (04:10 UTC)
        base = datetime(2026, 10, 17, 12, 0)  # = 19:45 NPT Oct 17
        for i in range(15):
            session.add(
                News(
                    symbol="NIFRA" if i % 2 else None,
                    date=date(2026, 10, 17),
                    title=f"NEPSE story {i}",
                    source="fake",
                    impact_score=100.0 - i,
                    url="https://x.test/a",
                    published_at=base + timedelta(hours=i),
                    headline_key=f"k{i}",
                    alt_sources=[],
                )
            )
        session.add(Watchlist(telegram_id=1, symbol="NIFRA"))
        session.commit()

    from nepse_sense.news.windows import window_from_arg

    window = window_from_arg("1", now=now)
    b = build_briefing(window, now, max_items=10)
    assert len(b.items) == 10  # capped at 10
    assert b.items[0].on_watchlist is True  # watchlist first
