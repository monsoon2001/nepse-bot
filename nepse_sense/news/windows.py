"""News time-window logic.

Trading days and the market session are config-driven (`TRADING_DAYS`,
`SESSION_OPEN`, `SESSION_CLOSE`) via MarketClock — nothing here hardcodes a
weekday. The trading calendar handles the weekend gap, so a briefing always
looks back to the previous trading day's close regardless of which weekdays
are configured.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from nepse_sense.calendar.trading_calendar import TradingCalendar
from nepse_sense.clock import MarketClock
from nepse_sense.config import settings

MAX_DAYS = 7  # /news N is capped at 7 days


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def _parse_hhmm(value: str, default: time) -> time:
    try:
        h, m = value.split(":")
        return time(int(h), int(m))
    except Exception:
        return default


def market_close_time() -> time:
    return _parse_hhmm(settings.session_close, time(15, 0))


def market_open_time() -> time:
    return _parse_hhmm(settings.session_open, time(11, 0))


def briefing_time() -> time:
    return _parse_hhmm(settings.news_briefing_time, time(10, 0))


def utc_naive(dt: datetime) -> datetime:
    """Convert aware datetime → naive UTC (storage format used across the DB)."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def to_local(dt: datetime) -> datetime:
    """Naive-UTC DB datetime → aware local (NPT)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(_tz())


@dataclass
class NewsWindow:
    start: datetime  # aware NPT
    end: datetime  # aware NPT
    label: str
    symbol: str | None = None

    @property
    def start_utc(self) -> datetime:
        return utc_naive(self.start)

    @property
    def end_utc(self) -> datetime:
        return utc_naive(self.end)

    @property
    def start_date(self) -> date:
        return self.start.date()


def since_last_close(
    now: datetime | None = None, calendar: TradingCalendar | None = None
) -> datetime:
    """Instant of the most recent market close at or before `now`.

    Uses the trading calendar, so the weekend gap is handled for whichever
    weekdays are configured in TRADING_DAYS.
    """
    cal = calendar or TradingCalendar()
    local = now.astimezone(_tz()) if now else datetime.now(_tz())
    today = local.date()
    # If we are on a trading day before the close, the last close is the
    # previous trading day's; at/after close it is today's.
    close_dt = datetime.combine(today, market_close_time(), tzinfo=_tz())
    if cal.is_trading_day(today) and local >= close_dt:
        return close_dt
    prev = cal.previous_trading_day(today)
    return datetime.combine(prev, market_close_time(), tzinfo=_tz())


def last_n_days(n: int, now: datetime | None = None) -> datetime:
    """`n` calendar days back from now (N clamped to 1..7)."""
    n = max(1, min(MAX_DAYS, int(n)))
    local = now.astimezone(_tz()) if now else datetime.now(_tz())
    return local - timedelta(days=n)


def since_last_briefing(
    now: datetime | None = None, cursor: datetime | None = None
) -> datetime:
    """Window start from the last *successful* briefing cursor (UTC-naive in DB).

    Falls back to the last market close when no successful briefing exists yet.
    """
    if cursor is not None:
        return to_local(cursor)
    return since_last_close(now)


def window_from_arg(
    arg: str | None = None,
    now: datetime | None = None,
    cursor: datetime | None = None,
) -> NewsWindow:
    """Parse a /news argument into a window.

    - None            → since last market close
    - "N" (1..7)      → last N calendar days (clamped to 7)
    - "SYMBOL"        → since last market close, filtered to that symbol
    """
    local = now.astimezone(_tz()) if now else datetime.now(_tz())
    end = local
    if arg is None or not arg.strip():
        start = since_last_close(local)
        return NewsWindow(start=start, end=end, label="since last market close")
    token = arg.strip()
    if token.isdigit():
        n = int(token)
        clamped = max(1, min(MAX_DAYS, n))
        start = last_n_days(clamped, local)
        label = f"last {clamped} day{'s' if clamped != 1 else ''}"
        if n > MAX_DAYS:
            label += f" (capped from {n})"
        return NewsWindow(start=start, end=end, label=label)
    # symbol filter (keeps the since-last-close default window)
    start = since_last_close(local)
    return NewsWindow(
        start=start, end=end, label="since last market close", symbol=token.upper()
    )


def window_for_briefing(now: datetime | None = None, cursor: datetime | None = None) -> NewsWindow:
    """Pre-market briefing window: last successful briefing → now."""
    local = now.astimezone(_tz()) if now else datetime.now(_tz())
    start = since_last_briefing(local, cursor)
    return NewsWindow(start=start, end=local, label="since last briefing")


def market_open_datetime(now: datetime) -> datetime:
    """Today's configured market open (same date as `now`)."""
    local = now.astimezone(_tz())
    return datetime.combine(local.date(), market_open_time(), tzinfo=_tz())


def in_trading_hours(now: datetime | None = None) -> bool:
    local = now.astimezone(_tz()) if now else datetime.now(_tz())
    return MarketClock().is_open(local)

