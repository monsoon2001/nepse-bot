"""MarketClock: single config-driven source of truth for NEPSE market time.

Replaces every hardcoded Sunday–Thursday assumption. Trading days, session
open/close and the post-close data grace period all come from settings
(`TRADING_DAYS`, `SESSION_OPEN`, `SESSION_CLOSE`, `DATA_GRACE_MINUTES`).

Default trading days are Mon–Fri because recent MeroLagani index dates include
Fridays and no Sundays. VERIFY against NEPSE — it has historically traded
Sun–Thu. Set ``TRADING_DAYS=sun,mon,tue,wed,thu`` for that calendar; nothing
below hardcodes a weekday.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from nepse_sense.calendar.trading_calendar import TradingCalendar
from nepse_sense.config import settings

# APScheduler day-of-week short names, indexed by Python weekday (Mon=0).
_CRON_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _parse_hhmm(value: str, default: time) -> time:
    try:
        h, m = str(value).split(":")
        return time(int(h), int(m))
    except Exception:
        return default


class MarketClock:
    """Trading-day + session-time abstraction driven entirely by config."""

    def __init__(self, calendar: TradingCalendar | None = None) -> None:
        self.calendar = calendar or TradingCalendar()
        self.timezone = ZoneInfo(settings.timezone)

    # -- config accessors ------------------------------------------------
    @property
    def trading_days(self) -> set[int]:
        return set(settings.trading_days)

    @property
    def session_open(self) -> time:
        return _parse_hhmm(settings.session_open, time(11, 0))

    @property
    def session_close(self) -> time:
        return _parse_hhmm(settings.session_close, time(15, 0))

    @property
    def data_grace_minutes(self) -> int:
        return max(0, int(settings.data_grace_minutes))

    # -- day checks ------------------------------------------------------
    def is_trading_day(self, dt: date) -> bool:
        """True if `dt` is a configured trading weekday and not a holiday."""
        return dt.weekday() in self.trading_days and not self.calendar.is_holiday(dt)

    def is_trading_today(self) -> bool:
        return self.is_trading_day(date.today())

    def is_open(self, now: datetime | None = None) -> bool:
        """True if the market session is currently open (day + within hours)."""
        local = now.astimezone(self.timezone) if now else datetime.now(self.timezone)
        if not self.is_trading_day(local.date()):
            return False
        return self.session_open <= local.time() < self.session_close

    def next_trading_day(self, dt: date) -> date:
        nd = dt + timedelta(days=1)
        while not self.is_trading_day(nd):
            nd += timedelta(days=1)
        return nd

    def previous_trading_day(self, dt: date) -> date:
        pd = dt - timedelta(days=1)
        while not self.is_trading_day(pd):
            pd -= timedelta(days=1)
        return pd

    # -- expected data day -----------------------------------------------
    def last_expected_trading_day(self, now: datetime | None = None) -> date:
        """Most recent day whose completed daily data should exist by `now`.

        Before close+grace we do not expect today's data yet; after that we do,
        walking back over non-trading days/holidays.
        """
        local = now.astimezone(self.timezone) if now else datetime.now(self.timezone)
        cutoff = datetime.combine(local.date(), self.session_close) + timedelta(
            minutes=self.data_grace_minutes
        )
        cutoff = cutoff.replace(tzinfo=self.timezone)
        d = local.date() if local >= cutoff else local.date() - timedelta(days=1)
        while not self.is_trading_day(d):
            d -= timedelta(days=1)
        return d

    # -- scheduler helper ------------------------------------------------
    def cron_day_string(self) -> str:
        """APScheduler `day_of_week` string from configured trading days."""
        return ",".join(_CRON_DAYS[d] for d in sorted(self.trading_days))

    def session_open_hour(self) -> int:
        return self.session_open.hour

    def session_close_hour(self) -> int:
        return self.session_close.hour

    def urgent_news_hours(self) -> str:
        """Hour range string for in-session urgent-news cron (open..close-1)."""
        start = self.session_open.hour
        end = max(start, self.session_close.hour - 1)
        return f"{start}-{end}"

    # -- data-driven consistency check -----------------------------------
    def infer_trading_weekdays(self, lookback_days: int = 90) -> set[int]:
        """Weekdays that actually appear in stored canonical prices."""
        from nepse_sense.db.engine import SessionLocal
        from nepse_sense.db.models import PriceCanonical

        since = date.today() - timedelta(days=lookback_days)
        db = SessionLocal()
        try:
            rows = (
                db.query(PriceCanonical.date)
                .filter(PriceCanonical.date >= since)
                .distinct()
                .all()
            )
        finally:
            db.close()
        return {d.weekday() for (d,) in rows if d is not None}

    def weekday_mismatch(self, lookback_days: int = 90) -> list[str]:
        """Human-readable warnings if stored data disagrees with config."""
        inferred = self.infer_trading_weekdays(lookback_days)
        if not inferred:
            return []
        configured = self.trading_days
        extra = inferred - configured
        missing = configured - inferred
        names = lambda ds: ",".join(_CRON_DAYS[d] for d in sorted(ds))  # noqa: E731
        warnings: list[str] = []
        if extra:
            warnings.append(
                f"prices exist on {names(extra)} but TRADING_DAYS excludes them"
            )
        if missing:
            warnings.append(
                f"TRADING_DAYS includes {names(missing)} but no recent prices on them"
            )
        return warnings


# Module-level convenience for callers that just need the day check.
def market_clock() -> MarketClock:
    return MarketClock()
