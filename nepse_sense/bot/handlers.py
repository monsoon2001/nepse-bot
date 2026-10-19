from __future__ import annotations

import asyncio
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import ContextTypes

from nepse_sense.bot.formatter import escape_html
from nepse_sense.bot.lookup import (
    find_symbol,
    get_symbol_universe,
    looks_like_ticker,
    signal_note,
    suggest_symbols,
    symbol_status,
)
from nepse_sense.bot.middleware import is_authorized
from nepse_sense.bot.ui import (
    back_keyboard,
    bullet,
    chart_keyboard,
    divider,
    footer,
    header,
    kv,
    main_menu_keyboard,
    score_bar,
    section,
    status_emoji,
    stock_keyboard,
    suggestion_keyboard,
)
from nepse_sense.clock import MarketClock
from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import (
    DataQualityIssue,
    Event,
    Fundamental,
    IndexDaily,
    IndicatorDaily,
    PortfolioHolding,
    PriceCanonical,
    ScanRun,
    Signal,
    SourceHealth,
    User,
    Watchlist,
)

DISCLAIMER = "Educational analysis, not financial advice."


# ------------------------------------------------------------------ access


async def authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.effective_user is None:
        return False
    if not is_authorized(update.effective_user.id):
        from nepse_sense.logging import logger

        logger.info(
            f"Unauthorized attempt from user_id={update.effective_user.id} "
            f"username={update.effective_user.username}"
        )
        if update.message:
            await update.message.reply_text("Unauthorized. Access denied.")
        return False
    return True


def _upsert_user(update: Update) -> User:
    """Create/refresh the user record with profile info from Telegram."""
    db = SessionLocal()
    tg = update.effective_user
    user = db.query(User).filter(User.telegram_id == tg.id).first()
    settings = dict(user.settings or {}) if user else {}
    settings.update(
        {
            "first_name": tg.first_name or "",
            "last_name": tg.last_name or "",
            "username": tg.username or "",
        }
    )
    if not user:
        user = User(telegram_id=tg.id, settings=settings, is_active=True)
        db.add(user)
    else:
        user.settings = settings
        user.updated_at = datetime.utcnow()
    db.commit()
    db.close()
    return user


# ------------------------------------------------------------------ screens


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """First screen: welcome + main menu."""
    if not await authorized(update, context):
        return
    _upsert_user(update)
    name = escape_html(update.effective_user.first_name or "there")
    text = "\n".join(
        [
            header("NEPSE Sense", "📈"),
            "",
            f"Welcome back, <b>{name}</b>.",
            "",
            "An explainable scanner for the Nepal Stock Exchange.",
            "Every signal ships with a score, plain-English reasons,",
            "risk flags and key levels — no black boxes.",
            "",
            section(
                "What's inside",
                [
                    bullet("Top Signals — ranked candidates, scored 0–100"),
                    bullet("Stock Report — technicals, fundamentals, reasoning"),
                    bullet("Chart — price with indicators"),
                    bullet("Watchlist & Portfolio — track what matters"),
                    bullet("Status & Profile — system health and your settings"),
                ],
                "🗂",
            ),
            "",
            "<i>Pick a button below, or type /help for all commands.</i>",
            "",
            footer(),
        ]
    )
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=main_menu_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Organized command reference."""
    if not await authorized(update, context):
        return
    text = "\n".join(
        [
            header("Help", "❓"),
            "",
            section(
                "Discover",
                [
                    bullet("/top — today's highest-conviction signals"),
                    bullet("/stock SYMBOL — full report with reasoning"),
                    bullet("/chart SYMBOL — price chart with indicators"),
                ],
                "🔍",
            ),
            "",
            section(
                "Market",
                [
                    bullet("/market — data coverage overview"),
                    bullet("/news [N|SYMBOL] — news since last close"),
                    bullet("/status — sources, last scan, open issues"),
                    bullet("/report — backtest performance summary"),
                    bullet("/brokers — broker data (unavailable in v1)"),
                ],
                "🌐",
            ),
            "",
            section(
                "Yours",
                [
                    bullet("/profile — account, activity, alert settings"),
                    bullet("/watchlist — symbols you follow"),
                    bullet("/add SYMBOL — add to watchlist"),
                    bullet("/remove SYMBOL — remove from watchlist"),
                    bullet("/portfolio — holdings and P/L"),
                ],
                "👤",
            ),
            "",
            section(
                "Tools",
                [
                    bullet("/addevent SYMBOL DATE TYPE [desc] — log a corporate event"),
                    bullet("/start — reopen the main menu"),
                ],
                "🛠",
            ),
            "",
            "<i>Commands with arguments: tap to copy, then add the symbol.</i>",
            "",
            footer(),
        ]
    )
    keyboard = [[InlineKeyboardButton("🔙 Back to menu", callback_data="menu:home")]]
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User profile: identity, activity, settings."""
    if not await authorized(update, context):
        return
    tg = update.effective_user
    user = _upsert_user(update)
    db = SessionLocal()
    wl_count = db.query(Watchlist).filter(Watchlist.telegram_id == tg.id).count()
    pf_count = (
        db.query(PortfolioHolding).filter(PortfolioHolding.telegram_id == tg.id).count()
    )
    ev_count = db.query(Event).count()
    alerts_on = bool((user.settings or {}).get("alerts_enabled", True))
    urgent_on = bool((user.settings or {}).get("urgent_alerts", False))
    db.close()
    created = user.created_at.strftime("%d %b %Y") if user.created_at else "—"
    uname = f"@{tg.username}" if tg.username else "not set"
    text = "\n".join(
        [
            header("Profile", "👤"),
            "",
            section(
                "Account",
                [
                    kv("Name", tg.first_name or "—"),
                    kv("Username", uname),
                    kv("User ID", tg.id),
                    kv("Access", "Authorized ✅"),
                    kv("Member since", created),
                ],
                "🪪",
            ),
            "",
            section(
                "Activity",
                [
                    kv("Watchlist", f"{wl_count} symbol{'s' if wl_count != 1 else ''}"),
                    kv("Portfolio", f"{pf_count} holding{'s' if pf_count != 1 else ''}"),
                    kv("Events logged", ev_count),
                ],
                "📊",
            ),
            "",
            section(
                "Settings",
                [
                    kv("Post-close alerts", "ON" if alerts_on else "OFF"),
                    kv("Urgent watchlist news", "ON" if urgent_on else "OFF"),
                    kv("Dedupe window", "1 day"),
                ],
                "⚙️",
            ),
            "",
            footer(),
        ]
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔕 Mute alerts" if alerts_on else "🔔 Unmute alerts",
                    callback_data="alerts:toggle",
                )
            ],
            [
                InlineKeyboardButton(
                    "⚡ Urgent ON" if urgent_on else "⚡ Urgent OFF",
                    callback_data="urgent:toggle",
                )
            ],
            [InlineKeyboardButton("🔙 Back to menu", callback_data="menu:home")],
        ]
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


# ------------------------------------------------------------------ signals


async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    db = SessionLocal()
    signals = db.query(Signal).order_by(Signal.score.desc()).limit(10).all()
    if not signals:
        await update.message.reply_text(
            "No signals available yet. Run a scan first.", reply_markup=back_keyboard()
        )
        db.close()
        return
    lines = [header("Top Signals", "📈"), ""]
    for s in signals:
        emoji = "🟢" if (s.score or 0) >= 60 else "🟡" if (s.score or 0) >= 35 else "🔴"
        lines.append(f"{emoji} <b>{escape_html(s.symbol)}</b> — {escape_html(s.type)}")
        lines.append(
            f"   <code>{score_bar(s.score or 0)}</code> {s.score:.0f}/100"
        )
    lines.append("")
    lines.append(f"{divider()}")
    lines.append(footer("Tap a symbol name to explore: /stock SYMBOL"))
    db.close()
    await update.message.reply_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=back_keyboard()
    )


async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: /stock SYMBOL\nExample: /stock NIFRA"
        )
        return
    await _lookup_and_reply(update, context.args[0])


def _muted_symbols(telegram_id: int) -> set[str]:
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    db.close()
    muted = (user.settings or {}).get("muted_symbols", []) if user else []
    return set(muted)


def _build_stock_report(
    db, symbol: str, muted: bool = False
) -> tuple[str, InlineKeyboardMarkup]:
    status, reason = symbol_status(db, symbol)
    if status == "unavailable":
        return (
            "\n".join(
                [
                    header(f"{symbol} — Unavailable", "⛔"),
                    "",
                    f"<code>{escape_html(symbol)}</code>: {escape_html(reason or 'no data')}",
                    "",
                    footer("No chart or signals are shown for unavailable data."),
                ]
            ),
            back_keyboard(),
        )
    pc = (
        db.query(PriceCanonical)
        .filter(PriceCanonical.symbol == symbol)
        .order_by(PriceCanonical.date.desc())
        .first()
    )
    if not pc:
        return (
            "\n".join(
                [
                    header("Not found", "⚠️"),
                    "",
                    f"Symbol <code>{escape_html(symbol)}</code> has no data.",
                    "",
                    footer("Check the symbol, or import data first."),
                ]
            ),
            back_keyboard(),
        )
    ind = (
        db.query(IndicatorDaily)
        .filter(IndicatorDaily.symbol == symbol)
        .order_by(IndicatorDaily.date.desc())
        .first()
    )
    fund = (
        db.query(Fundamental)
        .filter(Fundamental.symbol == symbol)
        .order_by(Fundamental.date.desc())
        .first()
    )
    sig = (
        db.query(Signal)
        .filter(Signal.symbol == symbol)
        .order_by(Signal.date.desc())
        .first()
    )
    lines = [
        header(symbol, "📈"),
        "",
        section(
            "Price",
            [
                kv("Last close", f"{pc.close:.2f}" if pc.close else "—", mono=True),
                kv("As of", pc.date),
                kv(
                    "Sources",
                    ", ".join(pc.sources) if pc.sources else "—",
                ),
            ],
            "💱",
        ),
    ]
    if ind:
        tech = []
        if ind.rsi14 is not None:
            rsi_emoji = "🟢" if 30 <= ind.rsi14 <= 70 else "🟡"
            tech.append(f"  {rsi_emoji} RSI  <code>{ind.rsi14:5.1f}</code>")
        if ind.ema20:
            tech.append(f"  EMA20 <code>{ind.ema20:8.2f}</code>")
        if ind.ema50:
            tech.append(f"  EMA50 <code>{ind.ema50:8.2f}</code>")
        if ind.atr14:
            tech.append(f"  ATR14 <code>{ind.atr14:8.2f}</code>")
        if ind.macd_line is not None and ind.macd_signal is not None:
            tech.append(f"  MACD  <code>{ind.macd_line:.3f} / {ind.macd_signal:.3f}</code>")
        lines.append("")
        lines.append(section("Technical", tech, "📊"))
    note = signal_note(db, symbol)
    lines.append("")
    if fund and fund.score:
        lines.append(
            section("Fundamentals", [kv("Quality score", f"{fund.score:.1f}/100")], "📑")
        )
    else:
        lines.append(section("Fundamentals", ["Unavailable"], "📑"))
    if sig:
        lines.append("")
        lines.append(
            section(
                "Signal",
                [
                    f"  {escape_html(sig.type)} — <code>{score_bar(sig.score or 0)}</code> "
                    f"{sig.score:.0f}/100",
                    f"  Confidence: {escape_html(sig.confidence_tier or '—')}",
                ],
                "🎯",
            )
        )
        if sig.reasons:
            lines.append("")
            lines.append(header("Why", "💡"))
            for r in sig.reasons[:6]:
                lines.append(bullet(r))
        if sig.risk_flags:
            lines.append("")
            lines.append(header("Risk flags", "⚠️"))
            for rf in sig.risk_flags[:5]:
                lines.append(f"  ⚠️ {escape_html(rf)}")
    elif note:
        lines.append("")
        lines.append(section("Signal", [escape_html(note)], "🎯"))
    lines.append("")
    lines.append(divider())
    lines.append(footer())
    return "\n".join(lines), stock_keyboard(symbol, muted=muted)


# ------------------------------------------------------------------ lookup


async def _lookup_and_reply(update: Update, token: str) -> None:
    """Resolve a typed token to a symbol and reply with card or suggestions."""
    universe = get_symbol_universe()
    exact = find_symbol(token, universe)
    if exact:
        db = SessionLocal()
        muted = exact in _muted_symbols(update.effective_user.id)
        text, markup = _build_stock_report(db, exact, muted=muted)
        db.close()
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
        return
    if looks_like_ticker(token):
        sugs = suggest_symbols(token, universe)
        if sugs:
            await update.message.reply_text(
                f"No exact match for <code>{escape_html(token.upper())}</code>. "
                "Tap a suggestion:",
                parse_mode="HTML",
                reply_markup=suggestion_keyboard(sugs),
            )
            return
    await update.message.reply_text(
        "I work with commands.\nType /help to see what I can do, "
        "or tap the button below.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🏠 Open menu", callback_data="menu:home")]]
        ),
    )


async def text_lookup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Plain text: exact symbol match → stock card, typo → suggestions."""
    if update.effective_user is None or not is_authorized(update.effective_user.id):
        return
    text = (update.message.text or "").strip()
    if not text or len(text) > 32:
        return
    await _lookup_and_reply(update, text)


async def unknown_command_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """`/nifra` etc. — unknown commands are treated as symbol lookups."""
    if update.effective_user is None or not is_authorized(update.effective_user.id):
        return
    raw = (update.message.text or "").strip()
    token = raw[1:].split()[0] if len(raw) > 1 else ""
    token = token.split("@")[0]  # strip @botname
    if not token:
        await update.message.reply_text(
            "Usage: /stock SYMBOL\nExample: /stock NIFRA"
        )
        return
    await _lookup_and_reply(update, token)


# ------------------------------------------------------------------ market


async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    from nepse_sense.indexing.service import latest_index_row, load_index_rows
    from nepse_sense.sources.adapters.merolagani_index import (
        compute_regime,
        format_market_message,
    )

    db = SessionLocal()
    clock = MarketClock()
    expected_last = clock.last_expected_trading_day()

    lines = [header("Market", "🌐"), ""]

    # NEPSE index regime (Unavailable when stale/short/disabled)
    rows = load_index_rows(db, "NEPSE")
    regime = compute_regime(rows, expected_last_day=expected_last)
    regime_lines = format_market_message(regime).splitlines()
    if regime_lines and "Educational analysis" in regime_lines[-1]:
        regime_lines.pop()  # single disclaimer added via footer()
    lines.append("\n".join(regime_lines))
    lines.append("")

    # Sector indices (any non-NEPSE index we have stored)
    names = [
        n for (n,) in db.query(IndexDaily.index_name).distinct().all() if n != "NEPSE"
    ]
    if names:
        sector_lines = []
        for name in sorted(names):
            row = latest_index_row(db, name)
            if row is not None:
                sector_lines.append(
                    f"  • {escape_html(str(name))}: <b>{row.value:,.2f}</b> "
                    f"({(row.pct_change or 0):+.2f}%)"
                )
        if sector_lines:
            lines.append(section("Sector indices", sector_lines, "📊"))
            lines.append("")

    total = db.query(PriceCanonical).count()
    symbols = db.query(PriceCanonical.symbol).distinct().count()
    sources = db.query(SourceHealth).all()
    lines.append(
        section(
            "Data coverage",
            [
                kv("Symbols", symbols),
                kv("Price rows", total),
                kv("Sources tracked", len(sources)),
            ],
            "🗄",
        )
    )
    lines.append("")
    if sources:
        src_lines = [
            f"  {status_emoji(s.status)} {escape_html(s.source_name)} — "
            f"{escape_html(s.status)}"
            for s in sources
        ]
        lines.append(section("Sources", src_lines, "🔌"))
    else:
        lines.append(section("Sources", ["No source health data yet."], "🔌"))
    lines.append("")
    lines.append(footer())
    db.close()
    await update.message.reply_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=back_keyboard()
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    db = SessionLocal()
    sources = db.query(SourceHealth).all()
    issues = (
        db.query(DataQualityIssue).filter(DataQualityIssue.resolved.is_(False)).count()
    )
    last_scan = db.query(ScanRun).order_by(ScanRun.started_at.desc()).first()
    total_symbols = db.query(PriceCanonical.symbol).distinct().count()
    total_signals = db.query(Signal).count()
    lines = [header("Status", "🧭"), ""]
    if sources:
        src_lines = [
            f"  {status_emoji(s.status)} {escape_html(s.source_name)} — "
            f"{escape_html(s.status)}\n"
            f"      last check {s.last_check}"
            for s in sources
        ]
        lines.append(section("Sources", src_lines, "🔌"))
    else:
        lines.append(section("Sources", ["No health checks recorded yet."], "🔌"))
    lines.append("")
    scan_lines = [
        kv("Last scan", last_scan.started_at if last_scan else "never"),
        kv("Symbols with data", total_symbols),
        kv("Signals stored", total_signals),
        kv("Open issues", issues, mono=True),
    ]
    if last_scan:
        scan_lines.insert(
            1,
            kv(
                "Scanned / excluded",
                f"{last_scan.symbols_processed} / {last_scan.symbols_excluded}",
            ),
        )
    lines.append(section("Pipeline", scan_lines, "⚙️"))
    lines.append("")
    # Calendar: config-driven trading days + weekday-vs-data consistency check
    from nepse_sense.clock import MarketClock

    clock = MarketClock()
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    cal_lines = [
        kv("Trading days", ",".join(day_names[d] for d in sorted(clock.trading_days))),
        kv("Session", f"{clock.session_open:%H:%M}–{clock.session_close:%H:%M}"),
        kv("Today is trading day", "yes" if clock.is_trading_today() else "no"),
    ]
    mismatches = clock.weekday_mismatch()
    if mismatches:
        cal_lines.append(kv("⚠️ Data/config mismatch", "; ".join(mismatches)))
    lines.append(section("Calendar", cal_lines, "📅"))
    lines.append("")
    lines.append(footer())
    db.close()
    await update.message.reply_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=back_keyboard()
    )


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    from nepse_sense.backtest.report import format_outcome_summary

    await update.message.reply_text(
        format_outcome_summary(), parse_mode="HTML", reply_markup=back_keyboard()
    )


async def brokers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    text = "\n".join(
        [
            header("Brokers", "🏦"),
            "",
            "Broker-level data is <b>unavailable in v1</b>.",
            "This screen is a placeholder for a future release.",
            "",
            footer(),
        ]
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=back_keyboard())


async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /chart SYMBOL\nExample: /chart NIFRA")
        return
    symbol = find_symbol(context.args[0]) or context.args[0].upper().strip()
    await _send_chart(update, symbol, days=180)


async def _send_chart(update: Update, symbol: str, days: int = 180):
    from nepse_sense.bot.chart import TIMEFRAMES, render_chart

    tf = next((k for k, v in TIMEFRAMES.items() if v == days), "6M")
    buf, as_of = await asyncio.to_thread(render_chart, symbol, days)
    if buf is None:
        await update.message.reply_text(
            f"No chart data for <code>{escape_html(symbol)}</code>.",
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        return
    caption = f"{escape_html(symbol)} — as of {as_of} · {tf}"
    try:
        await update.message.reply_photo(
            photo=buf,
            caption=caption,
            parse_mode="HTML",
            reply_markup=chart_keyboard(symbol, tf),
        )
    finally:
        buf.close()


# ------------------------------------------------------------------ watchlist


async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    db = SessionLocal()
    user_id = update.effective_user.id
    items = db.query(Watchlist).filter(Watchlist.telegram_id == user_id).all()
    if not items:
        db.close()
        text = "\n".join(
            [
                header("Watchlist", "👁"),
                "",
                "Your watchlist is empty.",
                "",
                "Add symbols with <code>/add SYMBOL</code>",
                "",
                footer(),
            ]
        )
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=back_keyboard()
        )
        return
    lines = [header("Watchlist", "👁"), ""]
    for w in items:
        sig = (
            db.query(Signal)
            .filter(Signal.symbol == w.symbol)
            .order_by(Signal.date.desc())
            .first()
        )
        if sig:
            emoji = "🟢" if (sig.score or 0) >= 60 else "🟡" if (sig.score or 0) >= 35 else "🔴"
            lines.append(
                f"{emoji} <b>{escape_html(w.symbol)}</b> — {escape_html(sig.type)} "
                f"({sig.score:.0f}/100)"
            )
        else:
            lines.append(f"⚪ <b>{escape_html(w.symbol)}</b> — no signal")
    lines.append("")
    lines.append(divider())
    lines.append(footer("Remove with /remove SYMBOL"))
    db.close()
    await update.message.reply_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=back_keyboard()
    )


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /add SYMBOL\nExample: /add NIFRA")
        return
    symbol = context.args[0].upper().strip()
    db = SessionLocal()
    user_id = update.effective_user.id
    existing = (
        db.query(Watchlist)
        .filter(Watchlist.telegram_id == user_id, Watchlist.symbol == symbol)
        .first()
    )
    if existing:
        text = f"👁 <b>{escape_html(symbol)}</b> is already in your watchlist."
    else:
        db.add(Watchlist(telegram_id=user_id, symbol=symbol))
        db.commit()
        text = f"👁 Added <b>{escape_html(symbol)}</b> to your watchlist."
    db.close()
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=back_keyboard("menu:watchlist")
    )


async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /remove SYMBOL")
        return
    symbol = context.args[0].upper().strip()
    db = SessionLocal()
    user_id = update.effective_user.id
    item = (
        db.query(Watchlist)
        .filter(Watchlist.telegram_id == user_id, Watchlist.symbol == symbol)
        .first()
    )
    if item:
        db.delete(item)
        db.commit()
        text = f"👁 Removed <b>{escape_html(symbol)}</b> from your watchlist."
    else:
        text = f"<b>{escape_html(symbol)}</b> is not in your watchlist."
    db.close()
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=back_keyboard("menu:watchlist")
    )


# ------------------------------------------------------------------ portfolio


async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    db = SessionLocal()
    user_id = update.effective_user.id
    holdings = (
        db.query(PortfolioHolding)
        .filter(PortfolioHolding.telegram_id == user_id)
        .all()
    )
    if not holdings:
        db.close()
        text = "\n".join(
            [
                header("Portfolio", "💼"),
                "",
                "No holdings tracked yet.",
                "",
                footer(),
            ]
        )
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=back_keyboard()
        )
        return
    lines = [header("Portfolio", "💼"), ""]
    total_pnl = 0.0
    for h in holdings:
        pc = (
            db.query(PriceCanonical)
            .filter(PriceCanonical.symbol == h.symbol)
            .order_by(PriceCanonical.date.desc())
            .first()
        )
        current = pc.close if pc and pc.close else h.buy_price
        pnl = (current - h.buy_price) * h.quantity
        total_pnl += pnl
        pct = ((current - h.buy_price) / h.buy_price * 100) if h.buy_price else 0
        arrow = "🟢" if pnl >= 0 else "🔴"
        lines.append(
            f"{arrow} <b>{escape_html(h.symbol)}</b>\n"
            f"   <code>{h.quantity:.0f} @ {h.buy_price:.2f} → {current:.2f}</code>\n"
            f"   {pct:+.1f}%  ({pnl:+.2f} NPR)"
        )
        lines.append("")
    lines.append(divider())
    arrow = "🟢" if total_pnl >= 0 else "🔴"
    lines.append(f"{arrow} <b>Total P/L:</b> {total_pnl:+.2f} NPR")
    lines.append("")
    lines.append(footer())
    db.close()
    await update.message.reply_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=back_keyboard()
    )


# ------------------------------------------------------------------ events


async def addevent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    if len(context.args) < 3:
        await update.message.reply_text(
            "<b>Add an event</b>\n\n"
            "Usage: <code>/addevent SYMBOL DATE TYPE [description]</code>\n"
            "Example: <code>/addevent NIFRA 2024-01-15 bonus 10% dividend</code>",
            parse_mode="HTML",
        )
        return
    from datetime import date as date_type

    symbol = context.args[0].upper().strip()
    try:
        dt = date_type.fromisoformat(context.args[1])
    except ValueError:
        await update.message.reply_text("Invalid date. Use YYYY-MM-DD.")
        return
    event_type = context.args[2]
    description = " ".join(context.args[3:]) if len(context.args) > 3 else ""
    db = SessionLocal()
    db.add(
        Event(
            symbol=symbol,
            date=dt,
            event_type=event_type,
            description=description,
            source="manual_addevent",
        )
    )
    db.commit()
    db.close()
    await update.message.reply_text(
        "\n".join(
            [
                header("Event added", "🗓"),
                "",
                kv("Symbol", symbol),
                kv("Date", dt),
                kv("Type", event_type),
                kv("Notes", description or "—"),
                "",
                footer(),
            ]
        ),
        parse_mode="HTML",
        reply_markup=back_keyboard(),
    )


# ------------------------------------------------------------------ callbacks


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline-menu navigation."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    if update.effective_user is None or not is_authorized(update.effective_user.id):
        await query.answer("Unauthorized.", show_alert=True)
        return
    await query.answer()
    action = query.data.split(":", 1)[1] if ":" in query.data else "home"
    fake_update = _make_fake_update(query)
    if action in ("home", "help"):
        handler = start_command if action == "home" else help_command
    elif action == "top":
        handler = top_command
    elif action == "news":
        handler = news_command
    elif action == "market":
        handler = market_command
    elif action == "watchlist":
        handler = watchlist_command
    elif action == "portfolio":
        handler = portfolio_command
    elif action == "status":
        handler = status_command
    elif action == "profile":
        handler = profile_command
    else:
        await query.edit_message_text("Unknown action.")
        return
    try:
        await handler(fake_update, context)
    except Exception:
        # If edit fails (identical content), fall back to a fresh message
        from nepse_sense.logging import logger

        logger.debug(f"menu callback fallback for action={action}")
        await query.message.reply_text("Open /start for the menu.", parse_mode="HTML")


def _make_fake_update(query):
    """Adapt a callback query so command handlers can reply in place (edits)."""
    return _CallbackUpdate(query)


class _CallbackUpdate:
    """Minimal Update stand-in: edits the message for text, sends new for photos."""

    def __init__(self, query):
        self.callback_query = query
        self.effective_user = query.from_user
        self.message = _EditTarget(query)


class _EditTarget:
    def __init__(self, query):
        self._query = query

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        try:
            await self._query.edit_message_text(
                text, parse_mode=parse_mode, reply_markup=reply_markup
            )
        except Exception:
            from nepse_sense.logging import logger

            logger.debug("edit_message_text failed, sending new message")
            await self._query.message.reply_text(
                text, parse_mode=parse_mode, reply_markup=reply_markup
            )

    async def reply_photo(self, photo, caption=None, parse_mode=None, reply_markup=None, **kwargs):
        # Photos can't be edited in place easily; send as a new message
        await self._query.message.reply_photo(
            photo, caption=caption, parse_mode=parse_mode, reply_markup=reply_markup
        )


async def alerts_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None:
        return
    if update.effective_user is None or not is_authorized(update.effective_user.id):
        await query.answer("Unauthorized.", show_alert=True)
        return
    db = SessionLocal()
    user = (
        db.query(User).filter(User.telegram_id == update.effective_user.id).first()
    )
    settings = dict(user.settings or {}) if user else {}
    new_state = not bool(settings.get("alerts_enabled", True))
    settings["alerts_enabled"] = new_state
    if user:
        user.settings = settings
        db.commit()
    db.close()
    await query.answer("Alerts " + ("enabled 🔔" if new_state else "muted 🔕"))
    await profile_command(_make_fake_update(query), context)


# ------------------------------------------------------------------ news


def _news_keyboard(page: int, pages: int, arg: str | None) -> InlineKeyboardMarkup:
    row: list[InlineKeyboardButton] = []
    if page > 1:
        row.append(
            InlineKeyboardButton(
                "◀ Prev", callback_data=f"news:page:{page - 1}:{arg or 'all'}"
            )
        )
    if page < pages:
        row.append(
            InlineKeyboardButton(
                "Next ▶", callback_data=f"news:page:{page + 1}:{arg or 'all'}"
            )
        )
    keyboard = [row] if row else []
    keyboard.append([InlineKeyboardButton("🔙 Back to menu", callback_data="menu:home")])
    return InlineKeyboardMarkup(keyboard)


async def _render_news(
    query_or_message,
    arg: str | None,
    page: int = 1,
    edit: bool = False,
):
    """Shared renderer for /news and its pagination buttons."""
    from nepse_sense.config import settings
    from nepse_sense.news.briefing import format_news_query, news_query_async

    q = await news_query_async(arg, limit=settings.news_max_items)
    text = format_news_query(q, page=page)
    _, page, pages = q.page(page)
    markup = _news_keyboard(page, pages, arg)
    if edit:
        await query_or_message.edit_message_text(
            text, parse_mode="HTML", reply_markup=markup
        )
    else:
        await query_or_message.reply_text(
            text, parse_mode="HTML", reply_markup=markup
        )


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/news [N|SYMBOL] — news since last market close, last N days, or one stock."""
    if not await authorized(update, context):
        return
    _upsert_user(update)
    arg = " ".join(context.args).strip() if context.args else None
    await _render_news(update.message, arg)


async def news_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pagination for /news: callback_data = news:page:<n>:<arg|all>."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    if update.effective_user is None or not is_authorized(update.effective_user.id):
        await query.answer("Unauthorized.", show_alert=True)
        return
    await query.answer()
    parts = query.data.split(":")  # news:page:<n>:<arg>
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
    arg = parts[3] if len(parts) > 3 and parts[3] != "all" else None
    try:
        await _render_news(query, arg, page=page, edit=True)
    except Exception:
        from nepse_sense.logging import logger

        logger.debug("news page edit failed, sending new message")
        await _render_news(query.message, arg, page=page)


async def urgent_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle per-user urgent watchlist alerts (default OFF)."""
    query = update.callback_query
    if query is None:
        return
    if update.effective_user is None or not is_authorized(update.effective_user.id):
        await query.answer("Unauthorized.", show_alert=True)
        return
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == update.effective_user.id).first()
    settings = dict(user.settings or {}) if user else {}
    new_state = not bool(settings.get("urgent_alerts", False))
    settings["urgent_alerts"] = new_state
    if user:
        user.settings = settings
        db.commit()
    db.close()
    await query.answer(
        "Urgent alerts " + ("enabled ⚡" if new_state else "disabled 🔕")
    )
    await profile_command(_make_fake_update(query), context)


async def stock_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle tech:/fund:/chart:/watch:/news:/alert:/card:/pick: inline buttons."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    if update.effective_user is None or not is_authorized(update.effective_user.id):
        await query.answer("Unauthorized.", show_alert=True)
        return
    await query.answer()
    parts = query.data.split(":")
    action = parts[0]
    symbol = (parts[1] if len(parts) > 1 else "").upper()
    timeframe = parts[2] if len(parts) > 2 and parts[2] in ("3M", "6M", "1Y") else "6M"

    if action == "pick":
        db = SessionLocal()
        muted = symbol in _muted_symbols(update.effective_user.id)
        text, markup = _build_stock_report(db, symbol, muted=muted)
        db.close()
        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            await query.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
        return

    if action == "card":
        db = SessionLocal()
        muted = symbol in _muted_symbols(update.effective_user.id)
        text, markup = _build_stock_report(db, symbol, muted=muted)
        db.close()
        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            await query.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
        return

    if action == "news":
        try:
            await _render_news(query, symbol, edit=True)
        except Exception:
            await _render_news(query.message, symbol)
        return

    if action == "alert":
        db = SessionLocal()
        user = (
            db.query(User).filter(User.telegram_id == update.effective_user.id).first()
        )
        settings = dict(user.settings or {}) if user else {}
        muted = set(settings.get("muted_symbols", []))
        if symbol in muted:
            muted.discard(symbol)
            answer = f"{symbol} alerts on 🔔"
        else:
            muted.add(symbol)
            answer = f"{symbol} alerts off 🔕"
        settings["muted_symbols"] = sorted(muted)
        if not user:
            user = User(
                telegram_id=update.effective_user.id,
                settings=settings,
                is_active=True,
            )
            db.add(user)
        else:
            user.settings = settings
        db.commit()
        text, markup = _build_stock_report(db, symbol, muted=symbol in muted)
        db.close()
        await query.answer(answer)
        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            await query.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
        return

    db = SessionLocal()
    if action == "tech":
        ind = (
            db.query(IndicatorDaily)
            .filter(IndicatorDaily.symbol == symbol)
            .order_by(IndicatorDaily.date.desc())
            .first()
        )
        if not ind:
            await query.message.reply_text(
                f"No technical data for {escape_html(symbol)}.", parse_mode="HTML"
            )
            db.close()
            return
        lines = [header(f"{symbol} — Technical", "📊"), ""]
        for label, val, fmt in [
            ("EMA20", ind.ema20, "{:.2f}"),
            ("EMA50", ind.ema50, "{:.2f}"),
            ("RSI14", ind.rsi14, "{:.1f}"),
            ("MACD line", ind.macd_line, "{:.3f}"),
            ("MACD signal", ind.macd_signal, "{:.3f}"),
            ("ATR14", ind.atr14, "{:.2f}"),
            ("Rel volume", ind.rel_volume, "{:.2f}x"),
            ("52w high", ind.high_52w, "{:.2f}"),
            ("52w low", ind.low_52w, "{:.2f}"),
        ]:
            if val is not None:
                lines.append(f"  <b>{label}:</b> <code>{fmt.format(val)}</code>")
        lines.append("")
        lines.append(divider())
        lines.append(footer())
        await query.message.reply_text(
            "\n".join(lines), parse_mode="HTML", reply_markup=back_keyboard()
        )
    elif action == "fund":
        fund = (
            db.query(Fundamental)
            .filter(Fundamental.symbol == symbol)
            .order_by(Fundamental.date.desc())
            .first()
        )
        if not fund:
            await query.message.reply_text(
                f"No fundamental data for {escape_html(symbol)}.", parse_mode="HTML"
            )
            db.close()
            return
        lines = [header(f"{symbol} — Fundamentals", "📑"), ""]
        rows = []
        for attr in (
            "eps",
            "pe_ratio",
            "book_value",
            "dividend_yield",
            "roe",
            "market_cap",
            "score",
        ):
            val = getattr(fund, attr, None)
            if val is not None:
                rows.append(kv(attr.replace("_", " ").title(), val))
        lines.extend(rows or ["Unavailable"])
        lines.append("")
        lines.append(divider())
        lines.append(footer())
        await query.message.reply_text(
            "\n".join(lines), parse_mode="HTML", reply_markup=back_keyboard()
        )
    elif action == "chart":
        from nepse_sense.bot.chart import TIMEFRAMES, render_chart

        days = TIMEFRAMES.get(timeframe, 180)
        buf, as_of = await asyncio.to_thread(render_chart, symbol, days)
        if buf is None:
            db.close()
            await query.message.reply_text(
                f"No chart data for {escape_html(symbol)}.", parse_mode="HTML"
            )
            return
        caption = f"{escape_html(symbol)} — as of {as_of} · {timeframe}"
        markup = chart_keyboard(symbol, timeframe)
        try:
            if query.message and query.message.photo:
                await query.edit_message_media(
                    media=InputMediaPhoto(buf, caption=caption, parse_mode="HTML"),
                    reply_markup=markup,
                )
            else:
                await query.message.reply_photo(
                    photo=buf,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
        finally:
            buf.close()
    elif action == "watch":
        user_id = update.effective_user.id
        existing = (
            db.query(Watchlist)
            .filter(Watchlist.telegram_id == user_id, Watchlist.symbol == symbol)
            .first()
        )
        if existing:
            db.delete(existing)
            db.commit()
            await query.message.reply_text(
                f"👁 Removed <b>{escape_html(symbol)}</b> from watchlist.",
                parse_mode="HTML",
                reply_markup=back_keyboard("menu:watchlist"),
            )
        else:
            db.add(Watchlist(telegram_id=user_id, symbol=symbol))
            db.commit()
            await query.message.reply_text(
                f"👁 Added <b>{escape_html(symbol)}</b> to watchlist.",
                parse_mode="HTML",
                reply_markup=back_keyboard("menu:watchlist"),
            )
    db.close()
