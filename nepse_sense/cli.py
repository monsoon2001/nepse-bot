import typer

from nepse_sense.db.setup import init_db
from nepse_sense.doctor import run_doctor
from nepse_sense.services.csv_import import CSVImporter

app = typer.Typer(help="NEPSE Sense CLI")


@app.command(name="init-db")
def init_db_cmd():
    """Initialize the database."""
    init_db()
    typer.echo("Database initialized")


@app.command()
def backfill(years: int = 5):
    """Backfill historical data."""
    typer.echo(f"Backfilling {years} years of data (stub - not implemented yet)")


@app.command()
def ingest():
    """Ingest daily data."""
    typer.echo("Ingesting data (stub - not implemented yet)")


@app.command()
def scan(date_str: str = typer.Option(None, help="Scan date YYYY-MM-DD (default: latest)")):
    """Run scan to generate signals."""
    from datetime import date as date_cls

    from nepse_sense.services.scanner import run_scan

    target = date_cls.fromisoformat(date_str) if date_str else None
    result = run_scan(target)
    if result["date"] is None:
        typer.echo("No price data found. Import data first.")
    else:
        typer.echo(
            f"Scan complete for {result['date']}: "
            f"{result['signals']} signals, "
            f"{result['scanned']} symbols, "
            f"{result['excluded']} excluded"
        )


@app.command()
def import_csv(
    file: str,
    import_type: str = typer.Option("prices", help="Type: prices, fundamentals, events"),
):
    """Import data from CSV file."""
    importer = CSVImporter()
    if import_type == "prices":
        count = importer.import_prices_csv(file)
        typer.echo(f"Imported {count} price records")
    elif import_type == "fundamentals":
        count = importer.import_fundamentals_csv(file)
        typer.echo(f"Imported {count} fundamental records")
    elif import_type == "events":
        count = importer.import_events_csv(file)
        typer.echo(f"Imported {count} event records")
    else:
        typer.echo("Invalid type. Use: prices, fundamentals, or events")
    importer.db.close()


@app.command()
def run_bot(demo: bool = False):
    """Run the Telegram bot."""
    from nepse_sense.bot.app import run_bot as _run_bot

    _run_bot(demo=demo)


@app.command()
def backtest(
    start: str = typer.Option(None, help="Start date YYYY-MM-DD"),
    end: str = typer.Option(None, help="End date YYYY-MM-DD"),
    min_score: float = typer.Option(50.0, help="Minimum signal score"),
    walk_forward: bool = typer.Option(False, help="Use walk-forward split"),
):
    """Run backtest on stored signals."""
    from datetime import date, timedelta

    from nepse_sense.backtest.engine import Backtester
    from nepse_sense.backtest.report import format_report

    end_date = date.fromisoformat(end) if end else date.today()
    start_date = date.fromisoformat(start) if start else end_date - timedelta(days=365)
    bt = Backtester()
    if walk_forward:
        result = bt.run_walk_forward(start_date, end_date, min_score=min_score)
    else:
        result = bt.run(start_date, end_date, min_score=min_score)
    typer.echo(format_report(result))
    bt.db.close()


@app.command()
def doctor():
    """Run system diagnostics."""
    run_doctor()


@app.command(name="index-sync")
def index_sync(index_name: str = typer.Option("NEPSE", help="Index name")):
    """Fetch the latest NEPSE/sector index slice and store it.

    Disabled unless ENABLE_MEROLAGANI=true. Automated access is prohibited by
    the source's Terms of Service (docs/DATA_SOURCES.md §8) — prefer
    import-index-csv.
    """
    from nepse_sense.indexing.service import sync_latest_index

    result = sync_latest_index(index_name=index_name)
    typer.echo(f"index-sync [{index_name}]: {result['status']} — {result['detail']}")
    if result["status"] == "disabled":
        typer.echo(
            "Automated fetching is off. Import a CSV instead:\n"
            "  nepse_sense import-index-csv <file.csv> --index-name NEPSE"
        )


@app.command(name="import-index-csv")
def import_index_csv_cmd(
    file: str,
    index_name: str = typer.Option("NEPSE", help="Index name"),
    source: str = typer.Option("csv", help="Source label for imported rows"),
):
    """Import index history from CSV (columns: date,value[,change,pct_change])."""
    from nepse_sense.db.engine import SessionLocal
    from nepse_sense.indexing.service import import_index_csv

    db = SessionLocal()
    try:
        count = import_index_csv(db, file, index_name=index_name, source=source)
        typer.echo(f"Imported {count} index rows for {index_name}")
    finally:
        db.close()


if __name__ == "__main__":
    app()
