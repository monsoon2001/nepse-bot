import os
from datetime import datetime

from sqlalchemy import text

from nepse_sense.config import settings
from nepse_sense.db.engine import engine
from nepse_sense.logging import setup_logging

setup_logging()

DEFAULT_TOKEN_PLACEHOLDER = "your_bot_token_here"  # noqa: S105


def run_doctor():
    """Run system diagnostics with pass/fail table."""
    print("\n" + "=" * 60)
    print("NEPSE Sense - Doctor Diagnostics")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Project Root: {settings.project_root}")
    print(f"DB URL: {settings.db_url}")
    print("=" * 60)
    print("\nDiagnostic Results:")
    print("-" * 60)

    checks = []
    # Check environment file
    env_exists = os.path.exists(".env")
    checks.append(
        (
            "Environment file (.env)",
            "PASS" if env_exists else "WARN - .env not found (using defaults)",
        )
    )

    # Check DB connection
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks.append(("Database connection", "PASS"))
    except Exception as e:
        checks.append(("Database connection", f"FAIL - {e}"))

    # Check DB tables exist
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            tables = [row[0] for row in result]
        required_tables = [
            "symbols",
            "prices_daily",
            "prices_canonical",
            "indicators_daily",
            "fundamentals",
            "events",
            "news",
            "signals",
            "signal_outcomes",
            "users",
            "watchlist",
            "portfolio_holdings",
            "alerts_sent",
            "source_health",
            "scan_runs",
            "data_quality_issues",
            "index_daily",
        ]
        missing = set(required_tables) - set(tables)
        if missing:
            checks.append(("Database tables", f"WARN - Missing: {', '.join(missing)}"))
        else:
            checks.append(("Database tables", "PASS"))
    except Exception as e:
        checks.append(("Database tables", f"FAIL - {e}"))

    # Check Telegram config
    if settings.telegram_bot_token and settings.telegram_bot_token != DEFAULT_TOKEN_PLACEHOLDER:
        checks.append(("Telegram bot token", "PASS"))
    else:
        checks.append(("Telegram bot token", "WARN - Not configured"))

    if settings.allowed_telegram_ids:
        checks.append(("Telegram allowed IDs", "PASS"))
    else:
        checks.append(("Telegram allowed IDs", "WARN - Not configured"))

    # Check directories
    data_dir = settings.data_dir
    cache_dir = settings.cache_dir
    checks.append(("Data directory", "PASS" if data_dir.exists() else "FAIL - missing"))
    checks.append(("Cache directory", "PASS" if cache_dir.exists() else "FAIL - missing"))

    # Calendar: trading-day config vs stored price data
    try:
        from nepse_sense.clock import MarketClock

        clock = MarketClock()
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        days = ",".join(day_names[d] for d in sorted(clock.trading_days))
        mismatches = clock.weekday_mismatch()
        if mismatches:
            checks.append(
                ("Calendar (TRADING_DAYS)", f"WARN - {days}; " + "; ".join(mismatches))
            )
        else:
            checks.append(("Calendar (TRADING_DAYS)", f"PASS - {days}"))
    except Exception as e:
        checks.append(("Calendar (TRADING_DAYS)", f"FAIL - {e}"))

    # Index source (MeroLagani) config + data freshness
    try:
        from datetime import date as _date

        if not settings.enable_merolagani:
            checks.append(
                (
                    "Index source (MeroLagani)",
                    "WARN - disabled (ENABLE_MEROLAGANI=false); see DATA_SOURCES.md s8",
                )
            )
        else:
            with engine.connect() as conn:
                res = conn.execute(
                    text("SELECT MAX(day) FROM index_daily WHERE source='merolagani'")
                )
                last = res.scalar()
            if last is None:
                checks.append(
                    ("Index source (MeroLagani)", "WARN - enabled but no data imported yet")
                )
            else:
                stale_days = (_date.today() - last).days
                if stale_days <= 4:
                    status = "PASS"
                else:
                    status = f"WARN - last data {stale_days}d old ({last})"
                checks.append(("Index source (MeroLagani)", status))
    except Exception as e:
        checks.append(("Index source (MeroLagani)", f"FAIL - {e}"))

    # Display table
    for name, status in checks:
        print(f"{name:<35} {status}")
    print("-" * 60)
    print(
        f"\nSummary: {sum(1 for _, s in checks if s.startswith('PASS'))} PASS, "
        f"{sum(1 for _, s in checks if s.startswith('WARN'))} WARN, "
        f"{sum(1 for _, s in checks if s.startswith('FAIL'))} FAIL"
    )
    print("=" * 60 + "\n")
