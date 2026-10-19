"""MeroLagani index adapter: parsing, validation, regime, storage, /market.

Adapted from the provided reference tests (plain asserts). The sqlite roundtrip
was replaced with SQLAlchemy upsert tests; last_expected_trading_day moved to
MarketClock. No test here touches the live network — HTTP is always faked.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from nepse_sense.clock import MarketClock
from nepse_sense.config import settings
from nepse_sense.db.engine import SessionLocal, engine
from nepse_sense.db.models import Base, DataQualityIssue, IndexDaily
from nepse_sense.indexing.service import (
    import_index_csv,
    load_index_rows,
    sync_latest_index,
    upsert_rows,
)
from nepse_sense.schemas.index import IndexRow
from nepse_sense.sources.adapters.merolagani_index import (
    MeroLaganiIndexSource,
    SourceError,
    compute_regime,
    format_market_message,
    parse_index_options,
    parse_index_table,
    parse_total_pages,
    validate_rows,
)

NPT = ZoneInfo("Asia/Kathmandu")

FIXTURE = """
<html><body>
<select name="ctl00$ContentPlaceHolder1$ddlIndexFilter">
  <option value="58">NEPSE</option><option value="57">Sensitive</option>
</select>
Showing 1 - 100 of 2899 records. [Total pages: 29]
<table class="table">
<tr><th>#</th><th>Date (AD)</th><th>Index Value</th>
<th>Absolute Change</th><th>Percentage Change</th></tr>
<tr><td>1</td><td>2026/10/16</td><td>2,634.17</td><td>8.23</td><td>0.31%</td></tr>
<tr><td>2</td><td>2026/10/15</td><td>2,625.93</td><td>4.67</td><td>0.17%</td></tr>
<tr><td>3</td><td>2026/10/14</td><td>2,621.26</td><td>21.32</td><td>0.82%</td></tr>
</table></body></html>
"""


def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def make_series(
    n: int,
    start: float = 2000.0,
    step: float = 3.0,
    end: date = date(2026, 10, 16),
    index_name: str = "NEPSE",
    source: str = "test",
) -> list[IndexRow]:
    """Synthetic consistent series on Mon-Fri, oldest first."""
    days, d = [], end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    rows, prev = [], None
    for i, day in enumerate(days):
        val = round(start + step * i, 2)
        chg = round(val - prev, 2) if prev else 0.0
        pct = round(chg / prev * 100, 2) if prev else 0.0
        rows.append(IndexRow(index_name, day, val, chg, pct, source))
        prev = val
    return rows


class FakeResponse:
    def __init__(self, text, status_code=200, headers=None):
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    """Minimal sync httpx.Client stand-in returning canned pages."""

    def __init__(self, texts):
        self._texts = texts
        self.calls = 0

    def request(self, method, url, data=None):
        text = self._texts[min(self.calls, len(self._texts) - 1)]
        self.calls += 1
        return FakeResponse(text)


class BoomClient:
    def request(self, *a, **k):
        raise RuntimeError("network down")


class FakeIndexSource:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def fetch_latest(self, index_name="NEPSE"):
        self.calls += 1
        return self.rows


# ---------------------------------------------------------------- parsing


def test_parse_table_handles_commas_and_percent():
    rows = parse_index_table(FIXTURE)
    assert len(rows) == 3
    assert rows[0].day == date(2026, 10, 16)
    assert rows[0].value == 2634.17 and rows[0].pct_change == 0.31


def test_parse_options_and_pages():
    assert parse_index_options(FIXTURE) == {"NEPSE": "58", "Sensitive": "57"}
    assert parse_total_pages(FIXTURE) == 29


def test_layout_change_raises():
    with pytest.raises(SourceError):
        parse_index_table("<html><body>no table</body></html>")


# -------------------------------------------------------------- validation


def test_fixture_rows_pass_validation():
    crit = [i for i in validate_rows(parse_index_table(FIXTURE)) if i.severity == "critical"]
    assert crit == []


def test_validation_catches_bad_data():
    rows = make_series(5)
    bad = rows[:]
    bad[3] = IndexRow("NEPSE", bad[3].day, bad[3].value, 99.0, bad[3].pct_change)
    codes = {i.code for i in validate_rows(bad)}
    assert "change_mismatch" in codes
    dup = rows + [rows[-1]]
    assert "duplicate" in {i.code for i in validate_rows(dup)}
    neg = rows[:]
    neg[0] = IndexRow("NEPSE", neg[0].day, -1.0, 0, 0)
    assert "non_positive" in {i.code for i in validate_rows(neg)}


# ------------------------------------------------------------------ regime


def test_regime_bullish_bearish_mixed():
    up = compute_regime(make_series(120, step=3.0))
    down = compute_regime(make_series(120, start=3000.0, step=-3.0))
    assert up.label == "Bullish" and down.label == "Bearish"
    rows = make_series(100, step=3.0)
    tail = rows[-1].value
    for i in range(1, 6):
        d = rows[-1].day + timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        v = round(tail - 25 * i, 2)
        rows.append(IndexRow("NEPSE", d, v, round(v - rows[-1].value, 2), 0.0))
    assert compute_regime(rows).label in ("Mixed", "Bearish")


def test_regime_refuses_short_or_stale_data():
    assert compute_regime(make_series(30)).label == "Unavailable"
    rows = make_series(120, end=date(2026, 10, 9))
    stale = compute_regime(rows, expected_last_day=date(2026, 10, 16))
    assert stale.label == "Unavailable" and stale.stale


def test_message_is_escaped_and_has_disclaimer():
    regime = compute_regime(make_series(120))
    regime.reasons.append("<script>x</script>")
    msg = format_market_message(regime)
    assert "&lt;script&gt;" in msg and "<script>" not in msg
    assert "not financial advice" in msg and "as of" in msg


# -------------------------------------------------------------- clock/config


def test_marketclock_mon_fri(monkeypatch):
    monkeypatch.setattr(settings, "trading_days", [0, 1, 2, 3, 4])
    clock = MarketClock()
    assert clock.is_trading_day(date(2026, 10, 16))  # Friday
    assert not clock.is_trading_day(date(2026, 10, 18))  # Sunday
    assert clock.cron_day_string() == "mon,tue,wed,thu,fri"


def test_marketclock_sun_thu_override(monkeypatch):
    monkeypatch.setattr(settings, "trading_days", [6, 0, 1, 2, 3])
    clock = MarketClock()
    assert clock.is_trading_day(date(2026, 10, 18))  # Sunday
    assert not clock.is_trading_day(date(2026, 10, 16))  # Friday
    assert clock.cron_day_string() == "mon,tue,wed,thu,sun"


def test_clock_last_expected_trading_day():
    clock = MarketClock()
    sat = datetime(2026, 10, 17, 12, 0, tzinfo=NPT)
    assert clock.last_expected_trading_day(sat) == date(2026, 10, 16)  # Friday
    mon_before_close = datetime(2026, 10, 19, 10, 0, tzinfo=NPT)
    assert clock.last_expected_trading_day(mon_before_close) == date(2026, 10, 16)
    mon_after_close = datetime(2026, 10, 19, 16, 0, tzinfo=NPT)
    assert clock.last_expected_trading_day(mon_after_close) == date(2026, 10, 19)


class _FakeCal:
    def __init__(self, holidays):
        self.holidays = set(holidays)

    def is_holiday(self, d):
        return d in self.holidays


def test_clock_last_expected_respects_holiday():
    clock = MarketClock(calendar=_FakeCal([date(2026, 10, 16)]))
    sat = datetime(2026, 10, 17, 12, 0, tzinfo=NPT)
    assert clock.last_expected_trading_day(sat) == date(2026, 10, 15)


def test_trading_days_field_validator():
    from nepse_sense.config import Settings

    s = Settings(_env_file=None, TRADING_DAYS="sun,mon,tue,wed,thu")
    assert s.trading_days == [0, 1, 2, 3, 6]
    s2 = Settings(_env_file=None, TRADING_DAYS="0,1,2,3,4")
    assert s2.trading_days == [0, 1, 2, 3, 4]


# ------------------------------------------------------------ storage/sync


def test_upsert_is_idempotent():
    setup_db()
    db = SessionLocal()
    rows = make_series(10)
    upsert_rows(db, rows)
    upsert_rows(db, rows)  # re-run must not duplicate
    loaded = load_index_rows(db, "NEPSE", source="test")
    assert len(loaded) == 10
    assert loaded[-1].day == rows[-1].day and loaded[-1].value == rows[-1].value
    assert db.query(IndexDaily).count() == 10
    db.close()


def test_sync_latest_index_disabled():
    setup_db()
    result = sync_latest_index(source=None)
    assert result["status"] == "disabled"
    assert result["upserted"] == 0


def test_sync_latest_index_with_source():
    setup_db()
    db = SessionLocal()
    src = FakeIndexSource(make_series(120, source="merolagani"))
    result = sync_latest_index(source=src, db=db)
    assert result["status"] == "ok" and result["upserted"] == 120
    assert src.calls == 1
    assert db.query(IndexDaily).count() == 120
    db.close()


def test_sync_records_critical_issues():
    setup_db()
    db = SessionLocal()
    rows = make_series(5, source="merolagani")
    rows[3] = IndexRow("NEPSE", rows[3].day, rows[3].value, 99.0, rows[3].pct_change)
    result = sync_latest_index(source=FakeIndexSource(rows), db=db)
    assert result["issues"] >= 1
    assert db.query(DataQualityIssue).filter_by(issue_type="change_mismatch").count() >= 1
    db.close()


def test_import_index_csv(tmp_path):
    setup_db()
    db = SessionLocal()
    csv_path = tmp_path / "nepse.csv"
    csv_path.write_text(
        "date,value\n2026-10-14,2621.26\n2026-10-15,2625.93\n2026-10-16,2634.17\n",
        encoding="utf-8",
    )
    n = import_index_csv(db, csv_path, index_name="NEPSE", source="csv")
    assert n == 3
    loaded = load_index_rows(db, "NEPSE", source="csv")
    assert len(loaded) == 3
    # change/pct computed from consecutive rows
    assert loaded[1].change == round(2625.93 - 2621.26, 2)
    assert loaded[-1].value == 2634.17
    db.close()


# ------------------------------------------------------------- http client


def test_fetch_latest_with_fake_client(tmp_path):
    src = MeroLaganiIndexSource(client=FakeClient([FIXTURE]), min_delay=0, cache_dir=tmp_path)
    rows = src.fetch_latest()
    assert len(rows) == 3 and rows[0].day == date(2026, 10, 16)


def test_circuit_breaker_opens(monkeypatch, tmp_path):
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)
    src = MeroLaganiIndexSource(
        client=BoomClient(), min_delay=0, max_retries=1, failure_threshold=1, cache_dir=tmp_path
    )
    with pytest.raises(SourceError):
        src.fetch_latest()
    with pytest.raises(SourceError, match="Circuit open"):
        src.fetch_latest()


def test_list_indices_with_fake_client(tmp_path):
    src = MeroLaganiIndexSource(client=FakeClient([FIXTURE]), min_delay=0, cache_dir=tmp_path)
    assert src.list_indices() == {"NEPSE": "58", "Sensitive": "57"}


# --------------------------------------------------------------- /market


def _make_update():
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 123
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


def _seed_nepse(end, n=120, step=3.0):
    db = SessionLocal()
    upsert_rows(db, make_series(n, step=step, end=end, source="merolagani"))
    db.close()


async def test_market_command_shows_regime():
    from nepse_sense.bot.handlers import market_command

    setup_db()
    end = MarketClock().last_expected_trading_day()
    _seed_nepse(end)
    db = SessionLocal()
    upsert_rows(db, make_series(30, end=end, index_name="Commercial Banks", source="merolagani"))
    db.close()

    update = _make_update()
    with patch("nepse_sense.bot.handlers.is_authorized", return_value=True):
        await market_command(update, MagicMock())
    text = update.message.reply_text.call_args[0][0]
    assert "Market regime" in text
    assert "Bullish" in text
    assert "Commercial Banks" in text
    assert "Educational analysis, not financial advice." in text


async def test_market_command_unavailable_when_no_data():
    from nepse_sense.bot.handlers import market_command

    setup_db()
    update = _make_update()
    with patch("nepse_sense.bot.handlers.is_authorized", return_value=True):
        await market_command(update, MagicMock())
    text = update.message.reply_text.call_args[0][0]
    assert "Unavailable" in text


async def test_market_command_unavailable_when_stale():
    from nepse_sense.bot.handlers import market_command

    setup_db()
    end = MarketClock().last_expected_trading_day() - timedelta(days=20)
    _seed_nepse(end)
    update = _make_update()
    with patch("nepse_sense.bot.handlers.is_authorized", return_value=True):
        await market_command(update, MagicMock())
    text = update.message.reply_text.call_args[0][0]
    assert "Unavailable" in text
    assert "stale" in text.lower()
