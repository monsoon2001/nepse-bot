"""Symbol lookup: exact match, fuzzy suggestions, availability status."""

from __future__ import annotations

import difflib
import re

from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import DataQualityIssue, PriceCanonical, Symbol

MIN_BARS = 10  # below this a card/chart is "Unavailable — insufficient history"
SIGNAL_MIN_BARS = 50  # signal engine gate (surfaced as a note, not Unavailable)

# tokens people type that should never be treated as ticker lookups
NOT_TICKERS = {
    "hi", "hey", "hello", "yo", "ok", "okay", "yes", "no", "thanks", "thank",
    "help", "menu", "start", "top", "market", "status", "report", "news",
    "profile", "watchlist", "portfolio", "brokers", "chart", "stock", "addevent",
    "who", "what", "when", "where", "why", "how", "test", "ping",
}


def get_symbol_universe() -> list[str]:
    """All known symbols: canonical price rows + the symbols master table."""
    with SessionLocal() as session:
        from_price = {
            r[0]
            for r in session.query(PriceCanonical.symbol).distinct().all()
            if r[0]
        }
        from_master = {
            r[0] for r in session.query(Symbol.symbol).distinct().all() if r[0]
        }
    return sorted(from_price | from_master)


def looks_like_ticker(token: str) -> bool:
    """Heuristic: short alphanumeric word that could plausibly be a symbol."""
    t = (token or "").strip()
    if not t or len(t) > 8:
        return False
    if t.lower() in NOT_TICKERS:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9]{2,8}", t))


def find_symbol(token: str, universe: list[str] | None = None) -> str | None:
    """Case-insensitive exact match → canonical (upper) symbol."""
    t = (token or "").strip()
    if not t:
        return None
    uni = universe if universe is not None else get_symbol_universe()
    upper = t.upper()
    if upper in uni:
        return upper
    lower_map = {s.lower(): s for s in uni}
    return lower_map.get(t.lower())


def suggest_symbols(token: str, universe: list[str] | None = None, n: int = 3) -> list[str]:
    """Fuzzy 'Did you mean' candidates for a mistyped symbol."""
    t = (token or "").strip()
    if not t:
        return []
    uni = universe if universe is not None else get_symbol_universe()
    if not uni:
        return []
    matches = difflib.get_close_matches(t.upper(), uni, n=n, cutoff=0.6)
    if matches:
        return matches
    # difflib is case-sensitive on the needle; try again with lowercase alphabet
    return difflib.get_close_matches(t.lower(), [s.lower() for s in uni], n=n, cutoff=0.6)


def symbol_status(db, symbol: str, asof=None) -> tuple[str, str | None]:
    """Availability of a symbol's data.

    Returns ("ok", None) when the card can render, or
    ("unavailable", reason) with a human-readable reason — never fake values.
    """
    from datetime import date as date_cls
    from datetime import timedelta

    bars = (
        db.query(PriceCanonical)
        .filter(PriceCanonical.symbol == symbol)
        .order_by(PriceCanonical.date.desc())
        .limit(1)
        .all()
    )
    if not bars:
        in_master = db.query(Symbol).filter(Symbol.symbol == symbol).first()
        if in_master:
            return "unavailable", "no price data imported yet"
        return "unavailable", "unknown symbol"

    latest = bars[0]
    count = (
        db.query(PriceCanonical)
        .filter(PriceCanonical.symbol == symbol)
        .count()
    )
    if count < MIN_BARS:
        return (
            "unavailable",
            f"insufficient history ({count} bar{'s' if count != 1 else ''}, need ≥{MIN_BARS})",
        )

    critical = (
        db.query(DataQualityIssue)
        .filter(
            DataQualityIssue.symbol == symbol,
            DataQualityIssue.severity == "critical",
            DataQualityIssue.resolved.is_(False),
        )
        .order_by(DataQualityIssue.date.desc())
        .first()
    )
    if critical:
        desc = critical.description or critical.issue_type or "validation failed"
        return "unavailable", f"failed validation: {desc}"

    ref = asof or date_cls.today()
    if latest.date and ref > latest.date:
        from nepse_sense.calendar.trading_calendar import TradingCalendar

        cal = TradingCalendar()
        missed = sum(
            1
            for i in range(1, (ref - latest.date).days + 1)
            if cal.is_trading_day(latest.date + timedelta(days=i))
        )
        if missed > 3:
            return "unavailable", f"data stale as of {latest.date}"

    return "ok", None


def signal_note(db, symbol: str) -> str | None:
    """Soft note when history is enough to display but not enough to signal."""
    count = (
        db.query(PriceCanonical)
        .filter(PriceCanonical.symbol == symbol)
        .count()
    )
    if MIN_BARS <= count < SIGNAL_MIN_BARS:
        return f"signals need ≥{SIGNAL_MIN_BARS} bars ({count} available)"
    return None
