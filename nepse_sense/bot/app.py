from telegram import BotCommand
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from nepse_sense.bot.handlers import (
    add_command,
    addevent_command,
    alerts_toggle_callback,
    brokers_command,
    chart_command,
    help_command,
    market_command,
    menu_callback,
    news_command,
    news_page_callback,
    portfolio_command,
    profile_command,
    remove_command,
    report_command,
    start_command,
    status_command,
    stock_callback,
    stock_command,
    text_lookup_handler,
    top_command,
    unknown_command_handler,
    urgent_toggle_callback,
    watchlist_command,
)
from nepse_sense.config import settings
from nepse_sense.logging import logger

# Organized command menu shown when the user types "/" in Telegram
BOT_COMMANDS = [
    BotCommand("start", "🏠 Open main menu"),
    BotCommand("top", "📈 Today's top signals"),
    BotCommand("stock", "📊 Full stock report — /stock SYMBOL"),
    BotCommand("chart", "📉 Price chart — /chart SYMBOL"),
    BotCommand("news", "📰 News since last close — /news [N|SYMBOL]"),
    BotCommand("market", "🌐 Market overview"),
    BotCommand("status", "🧭 System status"),
    BotCommand("report", "📋 Backtest report"),
    BotCommand("brokers", "🏦 Broker data (unavailable in v1)"),
    BotCommand("watchlist", "👁 Your watchlist"),
    BotCommand("add", "➕ Add to watchlist — /add SYMBOL"),
    BotCommand("remove", "➖ Remove from watchlist — /remove SYMBOL"),
    BotCommand("portfolio", "💼 Your holdings & P/L"),
    BotCommand("profile", "👤 Profile & alert settings"),
    BotCommand("addevent", "🛠 Log a corporate event — /addevent SYMBOL DATE TYPE [desc]"),
    BotCommand("help", "❓ All commands"),
]


async def _post_init(app: Application) -> None:
    """Set the grouped command menu + a simple description."""
    try:
        await app.bot.set_my_commands(BOT_COMMANDS)
        await app.bot.set_my_description(
            "Explainable NEPSE scanner. Rule-based signals with scores, "
            "reasons, risk flags and key levels — no black boxes. "
            "Educational only, not financial advice."
        )
        logger.info(f"Registered {len(BOT_COMMANDS)} bot commands")
    except Exception as e:
        logger.warning(f"Could not set bot commands: {e}")
    # bind the bot to the scheduler runtime bridge (briefing/urgent jobs send here)
    try:
        import asyncio

        from nepse_sense.jobs.runtime import bind_bot

        bind_bot(app.bot, asyncio.get_running_loop())
    except Exception as e:
        logger.warning(f"Could not bind bot to scheduler bridge: {e}")


def create_app() -> Application:
    app = Application.builder().token(settings.telegram_bot_token).post_init(
        _post_init
    ).build()
    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("top", top_command))
    app.add_handler(CommandHandler("stock", stock_command))
    app.add_handler(CommandHandler("market", market_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("brokers", brokers_command))
    app.add_handler(CommandHandler("chart", chart_command))
    app.add_handler(CommandHandler("watchlist", watchlist_command))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(CommandHandler("remove", remove_command))
    app.add_handler(CommandHandler("portfolio", portfolio_command))
    app.add_handler(CommandHandler("addevent", addevent_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("news", news_command))
    # Inline buttons (news:page before stock's news:SYMBOL)
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(alerts_toggle_callback, pattern=r"^alerts:"))
    app.add_handler(CallbackQueryHandler(urgent_toggle_callback, pattern=r"^urgent:"))
    app.add_handler(CallbackQueryHandler(news_page_callback, pattern=r"^news:page:"))
    app.add_handler(
        CallbackQueryHandler(
            stock_callback, pattern=r"^(tech|fund|chart|watch|news|alert|card|pick):"
        )
    )
    # Free text → symbol lookup; unknown /commands → symbol lookup
    from telegram.ext import MessageHandler, filters

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_lookup_handler)
    )
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command_handler))
    return app


def run_bot(demo: bool = False) -> None:
    if demo:
        logger.info("Seeding demo data...")
        from nepse_sense.bot.demo import seed_demo_data

        symbols = seed_demo_data()
        logger.info(f"Seeded demo data for: {symbols}")
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set. Configure .env first.")
        return
    app = create_app()
    logger.info("Starting NEPSE Sense bot (long polling)...")
    try:
        from nepse_sense.jobs.scheduler import start_background_scheduler

        start_background_scheduler()
    except Exception as e:
        logger.warning(f"Background scheduler not started: {e}")
    app.run_polling()
