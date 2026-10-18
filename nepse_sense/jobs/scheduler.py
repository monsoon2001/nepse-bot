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


def build_scheduler() -> BlockingScheduler:
    tz = settings.timezone
    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(
        job_ingest,
        CronTrigger(hour=15, minute=30, day_of_week="sun,mon,tue,wed,thu", timezone=tz),
        id="ingest",
        replace_existing=True,
    )
    scheduler.add_job(
        job_validate,
        CronTrigger(hour=15, minute=35, day_of_week="sun,mon,tue,wed,thu", timezone=tz),
        id="validate",
        replace_existing=True,
    )
    scheduler.add_job(
        job_indicators_signals_digest,
        CronTrigger(hour=15, minute=45, day_of_week="sun,mon,tue,wed,thu", timezone=tz),
        id="signals_digest",
        replace_existing=True,
    )
    scheduler.add_job(
        job_weekly_backfill,
        CronTrigger(hour=6, minute=0, day_of_week="sun", timezone=tz),
        id="weekly_backfill",
        replace_existing=True,
    )
    scheduler.add_job(
        job_source_health_ping,
        CronTrigger(minute="*/15", timezone=tz),
        id="health_ping",
        replace_existing=True,
    )
    return scheduler


def run_scheduler() -> None:
    scheduler = build_scheduler()
    logger.info(f"Starting scheduler (timezone={settings.timezone})...")
    scheduler.start()
