from __future__ import annotations

import hashlib
from datetime import date, timedelta

from nepse_sense.bot.formatter import escape_html
from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import AlertSent, PriceCanonical, Signal, User


def _is_stale_data(dt: date, max_age_days: int = 2) -> bool:
    return (date.today() - dt).days > max_age_days


def build_digest_message() -> str | None:
    """Build the daily post-close digest message. Returns None if stale."""
    db = SessionLocal()
    latest = db.query(PriceCanonical.date).order_by(PriceCanonical.date.desc()).first()
    if not latest:
        db.close()
        return None
    latest_date = latest[0]
    if _is_stale_data(latest_date):
        db.close()
        return None
    signals = (
        db.query(Signal)
        .filter(Signal.date >= latest_date)
        .order_by(Signal.score.desc())
        .limit(10)
        .all()
    )
    if not signals:
        db.close()
        return None
    lines = ["<b>Daily Digest</b>\n"]
    lines.append(f"Data as of: {latest_date}\n")
    for s in signals:
        lines.append(
            f"<b>{escape_html(s.symbol)}</b> — {escape_html(s.type)} — {s.score:.0f}/100"
        )
    lines.append("\n<i>Educational analysis, not financial advice.</i>")
    db.close()
    return "\n".join(lines)


def build_no_signals_message(reason: str) -> str:
    return (
        "<b>No signals today</b>\n"
        f"Reason: {escape_html(reason)}\n"
        "The latest available data is stale or unavailable, "
        "so no fresh signals were generated."
    )


def dedupe_alert(
    telegram_id: int,
    symbol: str,
    sig_type: str,
    dt: date,
    score: float,
    dedupe_days: int = 1,
) -> bool:
    """True if NEW (send), False if duplicate within dedupe window."""
    db = SessionLocal()
    cutoff = dt - timedelta(days=dedupe_days)
    existing = (
        db.query(AlertSent)
        .filter(
            AlertSent.telegram_id == telegram_id,
            AlertSent.symbol == symbol,
            AlertSent.date >= cutoff,
        )
        .all()
    )
    for e in existing:
        if e.signal_type == sig_type and abs((e.score or 0) - score) <= 10:
            db.close()
            return False
    key = f"{telegram_id}:{symbol}:{sig_type}:{dt}:{score}"
    msg_hash = hashlib.sha256(key.encode()).hexdigest()
    db.add(
        AlertSent(
            telegram_id=telegram_id,
            symbol=symbol,
            signal_type=sig_type,
            date=dt,
            score=score,
            message_hash=msg_hash,
        )
    )
    db.commit()
    db.close()
    return True


def get_users_with_alerts_enabled() -> list[User]:
    db = SessionLocal()
    users = db.query(User).filter(User.is_active.is_(True)).all()
    result = []
    for u in users:
        s = u.settings or {}
        if s.get("alerts_enabled", True):
            result.append(u)
    db.close()
    return result
