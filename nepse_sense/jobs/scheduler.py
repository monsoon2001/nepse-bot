from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from nepse_sense.config import settings
from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import ScanRun
from nepse_sense.logging import logger


def _log_scan_run(run_type: str, status: str, **kwargs) -> None:
    db = SessionLocal()
    run = ScanRun(run_type=run_type, status=status, started_at=datetime.utcnow())
    for k, v in kwargs.items():
        setattr(run, k, v)
    db.add(run)
    db.commit()
    db.close()


def job_ingest():
    logger.info("Scheduled job: ingest (stub - data ingestion)")
    _log_scan_run("ingest", "completed")


def job_index_fetch():
    """Post-close: fetch the NEPSE index (one GET) after close + grace.

    Idempotent (upserts by index_name+day+source). Disabled unless
    ENABLE_MEROLAGANI is set — see docs/DATA_SOURCES.md §8.
    """
    from nepse_sense.indexing.service import sync_latest_index

    if not _is_trading_today():
        return
    result = sync_latest_index()
    _log_scan_run(
        "index_fetch",
        result["status"],
        details={k: v for k, v in result.items() if k != "status"},
    )
    logger.info(f"Index fetch: {result['status']} ({result.get('detail', '')})")


def job_validate():
    logger.info("Scheduled job: validate + canonicalize (stub)")
    _log_scan_run("validate", "completed")


def job_indicators_signals_digest():
    logger.info("Scheduled job: indicators + signals + digest (stub)")
    _log_scan_run("scan", "completed")


def job_weekly_backfill():
    logger.info("Scheduled job: weekly backfill check (stub)")
    _log_scan_run("backfill", "completed")


def job_source_health_ping():
    logger.info("Scheduled job: source health ping (stub)")
    _log_scan_run("health_ping", "completed")


def _is_trading_today() -> bool:
    """False on NEPSE weekends and holidays (briefing/urgent jobs skip)."""
    from datetime import date

    from nepse_sense.calendar.trading_calendar import TradingCalendar

    return TradingCalendar().is_trading_day(date.today())


def job_premarket_briefing():
    """10:00 NPT Sun–Thu: pre-market briefing (news + today's events)."""
    import asyncio

    from nepse_sense.jobs.runtime import send_text_async
    from nepse_sense.news.briefing import run_briefing

    if not _is_trading_today():
        logger.info("Skipping pre-market briefing: market holiday/weekend")
        return
    logger.info("Scheduled job: pre-market briefing")
    run = asyncio.run(run_briefing(send=send_text_async))
    _log_scan_run(
        "news_briefing",
        run.status,
        signals_generated=len(run.briefing.items),
        details={"delivered_to": run.delivered_to, "detail": run.detail},
    )
    logger.info(
        f"Pre-market briefing {run.status}: {len(run.briefing.items)} item(s), "
        f"delivered to {run.delivered_to} user(s)"
    )


def job_urgent_news():
    """Every 15 min during market hours: opt-in urgent watchlist alerts."""
    import asyncio

    from nepse_sense.jobs.runtime import send_text_async
    from nepse_sense.news.urgent import run_urgent_news

    if not _is_trading_today():
        return
    run = asyncio.run(run_urgent_news(send=send_text_async))
    if run.status == "success" and run.delivered:
        logger.info(f"Urgent news alerts: {run.delivered} delivered ({len(run.items)} items)")
        _log_scan_run(
            "urgent_news",
            "completed",
            signals_generated=len(run.items),
            details={"delivered": run.delivered},
        )


def build_scheduler(background: bool = False):
    from nepse_sense.clock import MarketClock

    tz = settings.timezone
    clock = MarketClock()
    days = clock.cron_day_string()  # config-driven, e.g. "mon,tue,wed,thu,fri"
    if background:
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler(timezone=tz)
    else:
        scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(
        job_ingest,
        CronTrigger(hour=15, minute=30, day_of_week=days, timezone=tz),
        id="ingest",
        replace_existing=True,
    )
    scheduler.add_job(
        job_index_fetch,
        CronTrigger(
            hour=clock.session_close_hour(),
            minute=clock.data_grace_minutes,
            day_of_week=days,
            timezone=tz,
        ),
        id="index_fetch",
        replace_existing=True,
    )
    scheduler.add_job(
        job_validate,
        CronTrigger(hour=15, minute=35, day_of_week=days, timezone=tz),
        id="validate",
        replace_existing=True,
    )
    scheduler.add_job(
        job_indicators_signals_digest,
        CronTrigger(hour=15, minute=45, day_of_week=days, timezone=tz),
        id="signals_digest",
        replace_existing=True,
    )
    scheduler.add_job(
        job_weekly_backfill,
        CronTrigger(hour=6, minute=0, day_of_week=days.split(",")[0], timezone=tz),
        id="weekly_backfill",
        replace_existing=True,
    )
    scheduler.add_job(
        job_source_health_ping,
        CronTrigger(minute="*/15", timezone=tz),
        id="health_ping",
        replace_existing=True,
    )
    # News: pre-market briefing at configured time, urgent alerts in-session
    scheduler.add_job(
        job_premarket_briefing,
        CronTrigger(
            hour=int(settings.news_briefing_time.split(":")[0]),
            minute=int(settings.news_briefing_time.split(":")[1]),
            day_of_week=days,
            timezone=tz,
        ),
        id="news_briefing",
        replace_existing=True,
    )
    scheduler.add_job(
        job_urgent_news,
        CronTrigger(
            minute="*/15",
            hour=clock.urgent_news_hours(),
            day_of_week=days,
            timezone=tz,
        ),
        id="urgent_news",
        replace_existing=True,
    )
    return scheduler


def run_scheduler() -> None:
    scheduler = build_scheduler()
    logger.info(f"Starting scheduler (timezone={settings.timezone})...")
    scheduler.start()


def start_background_scheduler():
    """Start the scheduler in a daemon thread (used inside the bot process)."""
    import threading

    scheduler = build_scheduler(background=True)
    thread = threading.Thread(target=scheduler.start, name="nepse-scheduler", daemon=True)
    thread.start()
    logger.info(f"Background scheduler started ({len(scheduler.get_jobs())} jobs)")
    return scheduler
