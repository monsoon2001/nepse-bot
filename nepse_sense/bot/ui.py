"""Shared Telegram UI helpers: consistent headers, sections, keyboards, menu."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from nepse_sense.bot.formatter import escape_html

DISCLAIMER = "<i>Educational analysis, not financial advice.</i>"

# ---------------------------------------------------------------- formatting


def header(title: str, emoji: str = "") -> str:
    prefix = f"{emoji} " if emoji else ""
    return f"<b>{prefix}{escape_html(title)}</b>"


def section(title: str, lines: list[str], emoji: str = "") -> str:
    body = "\n".join(lines) if lines else "<i>None</i>"
    return f"{header(title, emoji)}\n{body}"


def kv(label: str, value, mono: bool = False) -> str:
    v = "—" if value is None or value == "" else str(value)
    if mono:
        v = f"<code>{escape_html(v)}</code>"
    else:
        v = escape_html(v)
    return f"  <b>{escape_html(label)}:</b> {v}"


def bullet(text: str) -> str:
    return f"  • {escape_html(str(text))}"


def divider() -> str:
    return "——————————————————"


def footer(extra: str = "") -> str:
    parts = []
    if extra:
        parts.append(f"<i>{escape_html(extra)}</i>")
    parts.append(DISCLAIMER)
    return "\n".join(parts)


def score_bar(score: float, width: int = 10) -> str:
    """Visual 0-100 score bar using unicode blocks."""
    filled = max(0, min(width, round(score / 100 * width)))
    return "▰" * filled + "▱" * (width - filled)


def status_emoji(status: str) -> str:
    s = (status or "").lower()
    if s in ("ok", "healthy", "pass", "up"):
        return "🟢"
    if s in ("degraded", "warn", "slow", "partial"):
        return "🟡"
    if s in ("fail", "down", "error", "critical"):
        return "🔴"
    return "⚪"


# ---------------------------------------------------------------- keyboards


def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("📈 Top Signals", callback_data="menu:top"),
            InlineKeyboardButton("🌐 Market", callback_data="menu:market"),
        ],
        [
            InlineKeyboardButton("👁 Watchlist", callback_data="menu:watchlist"),
            InlineKeyboardButton("💼 Portfolio", callback_data="menu:portfolio"),
        ],
        [
            InlineKeyboardButton("🧭 Status", callback_data="menu:status"),
            InlineKeyboardButton("👤 Profile", callback_data="menu:profile"),
        ],
        [
            InlineKeyboardButton("❓ Help", callback_data="menu:help"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def stock_keyboard(
    symbol: str, muted: bool = False, has_chart: bool = True
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_chart:
        rows.append([InlineKeyboardButton("📈 Chart", callback_data=f"chart:{symbol}:6M")])
    rows.append(
        [
            InlineKeyboardButton("📊 Technical", callback_data=f"tech:{symbol}"),
            InlineKeyboardButton("📑 Fundamentals", callback_data=f"fund:{symbol}"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                "🔔 Alert on" if not muted else "🔕 Alert off",
                callback_data=f"alert:{symbol}",
            ),
            InlineKeyboardButton("👁 Watchlist", callback_data=f"watch:{symbol}"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton("📰 News", callback_data=f"news:{symbol}"),
            InlineKeyboardButton("🔙 Back to menu", callback_data="menu:home"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def chart_keyboard(symbol: str, timeframe: str = "6M") -> InlineKeyboardMarkup:
    """Timeframe selector for an already-sent chart photo."""
    tf_buttons = [
        InlineKeyboardButton(
            f"{'✅ ' if tf == timeframe else ''}{tf}",
            callback_data=f"chart:{symbol}:{tf}",
        )
        for tf in ("3M", "6M", "1Y")
    ]
    return InlineKeyboardMarkup(
        [
            tf_buttons,
            [
                InlineKeyboardButton("🔙 Back to card", callback_data=f"card:{symbol}"),
                InlineKeyboardButton("🏠 Menu", callback_data="menu:home"),
            ],
        ]
    )


def suggestion_keyboard(symbols: list[str]) -> InlineKeyboardMarkup:
    """'Did you mean' buttons for mistyped symbols."""
    rows = [
        [InlineKeyboardButton(f"Did you mean {s}?", callback_data=f"pick:{s}")]
        for s in symbols[:3]
    ]
    rows.append([InlineKeyboardButton("🔙 Back to menu", callback_data="menu:home")])
    return InlineKeyboardMarkup(rows)


def back_keyboard(target: str = "menu:home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Back to menu", callback_data=target)]]
    )
