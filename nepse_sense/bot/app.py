from telegram.ext import Application, CommandHandler

from nepse_sense.bot.handlers import (
    add_command,
    addevent_command,
    brokers_command,
    chart_command,
    help_command,
    market_command,
    portfolio_command,
    remove_command,
    report_command,
    start_command,
    status_command,
    stock_command,
    top_command,
    watchlist_command,
)
from nepse_sense.config import settings
from nepse_sense.logging import logger


def create_app() -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
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
    app.run_polling()
