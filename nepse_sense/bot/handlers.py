from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from nepse_sense.bot.formatter import escape_html
from nepse_sense.bot.middleware import is_authorized
from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import (
    DataQualityIssue,
    Fundamental,
    IndicatorDaily,
    PriceCanonical,
    Signal,
    SourceHealth,
)


async def authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.effective_user is None:
        return False
    if not is_authorized(update.effective_user.id):
        if update.message:
            await update.message.reply_text("Unauthorized.")
        return False
    return True


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    await update.message.reply_text(
        "<b>NEPSE Sense Bot</b>\n\n"
        "Available commands:\n"
        "/start /help /buy /sell /top /stock SYMBOL /market /news /events\n"
        "/bulk /watchlist /add SYMBOL /remove SYMBOL /alerts /settings /status /report\n"
        "/support SYMBOL /fundamental SYMBOL /compare A B /risk SYMBOL PRICE /chart SYMBOL\n"
        "/portfolio /brokers /addevent\n\n"
        "<i>Educational analysis, not financial advice.</i>",
        parse_mode="HTML",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    await update.message.reply_text(
        "<b>Help</b>\n\n"
        "/stock SYMBOL — Full stock report with buttons\n"
        "/top — Top signals\n"
        "/market — Market overview\n"
        "/chart SYMBOL — Price chart with indicators\n"
        "/add SYMBOL — Add to watchlist\n"
        "/status — Source health and scan status\n"
        "/brokers — Broker data (unavailable in v1)\n\n"
        "<i>Educational analysis, not financial advice.</i>",
        parse_mode="HTML",
    )


async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    db = SessionLocal()
    signals = (
        db.query(Signal)
        .order_by(Signal.score.desc())
        .limit(10)
        .all()
    )
    if not signals:
        await update.message.reply_text("No signals available yet. Run a scan first.")
        db.close()
        return
    lines = ["<b>Top Signals</b>\n"]
    for s in signals:
        lines.append(
            f"{escape_html(s.symbol)} — {escape_html(s.type)} — {s.score:.0f}/100"
        )
    lines.append("\n<i>Educational analysis, not financial advice.</i>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    db.close()


async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /stock SYMBOL")
        return
    symbol = context.args[0].upper().strip()
    db = SessionLocal()
    pc = (
        db.query(PriceCanonical)
        .filter(PriceCanonical.symbol == symbol)
        .order_by(PriceCanonical.date.desc())
        .first()
    )
    if not pc:
        await update.message.reply_text(f"Symbol {escape_html(symbol)} not found.")
        db.close()
        return
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
    lines = [f"<b>{escape_html(symbol)}</b>"]
    lines.append(f"Last close: {pc.close:.2f}")
    lines.append(f"Data date: {pc.date}")
    lines.append(f"Sources: {', '.join(pc.sources) if pc.sources else 'N/A'}")
    if ind:
        lines.append(f"RSI14: {ind.rsi14:.1f}" if ind.rsi14 else "RSI14: N/A")
        lines.append(f"ATR14: {ind.atr14:.2f}" if ind.atr14 else "ATR14: N/A")
    if fund:
        if fund.score:
            lines.append(f"Fundamental score: {fund.score:.1f}")
        else:
            lines.append("Fundamental: Unavailable")
    else:
        lines.append("Fundamentals: Unavailable")
    if sig:
        lines.append(f"\nSignal: <b>{escape_html(sig.type)}</b> — {sig.score:.0f}/100")
        if sig.reasons:
            lines.append("Reasons:")
            for r in sig.reasons[:5]:
                lines.append(f"  • {escape_html(r)}")
    lines.append("\n<i>Educational analysis, not financial advice.</i>")
    keyboard = [
        [
            InlineKeyboardButton("Technical", callback_data=f"tech:{symbol}"),
            InlineKeyboardButton("Fundamentals", callback_data=f"fund:{symbol}"),
        ],
        [
            InlineKeyboardButton("Chart", callback_data=f"chart:{symbol}"),
            InlineKeyboardButton("Alert", callback_data=f"alert:{symbol}"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=reply_markup
    )
    db.close()


async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    db = SessionLocal()
    total = db.query(PriceCanonical).count()
    sources = db.query(SourceHealth).all()
    lines = ["<b>Market Overview</b>\n"]
    lines.append(f"Total canonical price rows: {total}")
    lines.append(f"Sources tracked: {len(sources)}")
    for s in sources:
        lines.append(f"  {escape_html(s.source_name)}: {escape_html(s.status)}")
    lines.append("\n<i>Educational analysis, not financial advice.</i>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    db.close()


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    db = SessionLocal()
    from nepse_sense.db.models import ScanRun, Signal

    sources = db.query(SourceHealth).all()
    issues = db.query(DataQualityIssue).filter(DataQualityIssue.resolved.is_(False)).count()
    last_scan = db.query(ScanRun).order_by(ScanRun.started_at.desc()).first()
    total_symbols = db.query(PriceCanonical.symbol).distinct().count()
    total_signals = db.query(Signal).count()
    lines = ["<b>Status</b>\n"]
    lines.append("<b>Source health:</b>")
    if not sources:
        lines.append("  No source health data yet.")
    for s in sources:
        last_ok = s.last_success.strftime("%Y-%m-%d %H:%M") if s.last_success else "never"
        lines.append(
            f"  {escape_html(s.source_name)}: {escape_html(s.status)} "
            f"(last check: {s.last_check}, last success: {last_ok})"
        )
    lines.append(f"\nLast scan: {last_scan.started_at if last_scan else 'never'}")
    if last_scan:
        lines.append(
            f"  scanned: {last_scan.symbols_processed}, "
            f"excluded: {last_scan.symbols_excluded}"
        )
    lines.append(f"Symbols with data: {total_symbols}")
    lines.append(f"Total signals stored: {total_signals}")
    lines.append(f"Open data-quality issues: {issues}")
    lines.append("\n<i>Educational analysis, not financial advice.</i>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    db.close()


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    from nepse_sense.backtest.report import format_outcome_summary

    await update.message.reply_text(format_outcome_summary(), parse_mode="HTML")


async def brokers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    await update.message.reply_text(
        "<b>Broker data is currently unavailable in v1.</b>\n"
        "Broker-level data is not supported yet.\n\n"
        "<i>Educational analysis, not financial advice.</i>",
        parse_mode="HTML",
    )


async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /chart SYMBOL")
        return
    symbol = context.args[0].upper().strip()
    from nepse_sense.bot.chart import render_chart

    buf = render_chart(symbol)
    if not buf:
        await update.message.reply_text(f"No data available for {escape_html(symbol)}.")
        return
    await update.message.reply_photo(photo=buf, caption=f"{escape_html(symbol)} chart")


async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    db = SessionLocal()
    user_id = update.effective_user.id
    from nepse_sense.db.models import Watchlist

    items = db.query(Watchlist).filter(Watchlist.telegram_id == user_id).all()
    if not items:
        await update.message.reply_text("Watchlist empty. Use /add SYMBOL to add.")
        db.close()
        return
    lines = ["<b>Your Watchlist</b>\n"]
    for w in items:
        lines.append(f"• {escape_html(w.symbol)}")
    lines.append("\n<i>Educational analysis, not financial advice.</i>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    db.close()


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /add SYMBOL")
        return
    symbol = context.args[0].upper().strip()
    db = SessionLocal()
    from nepse_sense.db.models import Watchlist

    user_id = update.effective_user.id
    existing = (
        db.query(Watchlist)
        .filter(Watchlist.telegram_id == user_id, Watchlist.symbol == symbol)
        .first()
    )
    if existing:
        await update.message.reply_text(f"{escape_html(symbol)} already in watchlist.")
    else:
        db.add(Watchlist(telegram_id=user_id, symbol=symbol))
        db.commit()
        await update.message.reply_text(f"Added {escape_html(symbol)} to watchlist.")
    db.close()


async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /remove SYMBOL")
        return
    symbol = context.args[0].upper().strip()
    db = SessionLocal()
    from nepse_sense.db.models import Watchlist

    user_id = update.effective_user.id
    item = (
        db.query(Watchlist)
        .filter(Watchlist.telegram_id == user_id, Watchlist.symbol == symbol)
        .first()
    )
    if item:
        db.delete(item)
        db.commit()
        await update.message.reply_text(f"Removed {escape_html(symbol)} from watchlist.")
    else:
        await update.message.reply_text(f"{escape_html(symbol)} not in watchlist.")
    db.close()


async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    db = SessionLocal()
    user_id = update.effective_user.id
    from nepse_sense.db.models import PortfolioHolding, PriceCanonical

    holdings = (
        db.query(PortfolioHolding)
        .filter(PortfolioHolding.telegram_id == user_id)
        .all()
    )
    if not holdings:
        await update.message.reply_text("No portfolio holdings.")
        db.close()
        return
    lines = ["<b>Portfolio</b>\n"]
    total_pnl = 0.0
    for h in holdings:
        pc = (
            db.query(PriceCanonical)
            .filter(PriceCanonical.symbol == h.symbol)
            .order_by(PriceCanonical.date.desc())
            .first()
        )
        current = pc.close if pc else h.buy_price
        pnl = (current - h.buy_price) * h.quantity
        total_pnl += pnl
        pnl_pct = ((current - h.buy_price) / h.buy_price * 100) if h.buy_price else 0
        lines.append(
            f"{escape_html(h.symbol)}: {h.quantity:.0f} @ {h.buy_price:.2f} → "
            f"{current:.2f} ({pnl_pct:+.1f}%, {pnl:+.2f})"
        )
    lines.append(f"\nTotal P/L: {total_pnl:+.2f}")
    lines.append("\n<i>Educational analysis, not financial advice.</i>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    db.close()


async def addevent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized(update, context):
        return
    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage: /addevent SYMBOL DATE EVENT_TYPE [DESCRIPTION]\n"
            "Example: /addevent NIFRA 2024-01-15 bonus 10% bonus dividend"
        )
        return
    from datetime import date as date_type

    from nepse_sense.db.models import Event

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
        f"Event added: {escape_html(symbol)} — {escape_html(event_type)} on {dt}"
    )
