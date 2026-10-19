"""Index storage + sync service (NEPSE / sector indices).

Bridges the MeroLagani adapter (parse/fetch) to the `IndexDaily` table and the
`data_quality_issues` table. Idempotent: upserts by (index_name, day, source).

Automated fetching is disabled by default (ENABLE_MEROLAGANI=false — see
docs/DATA_SOURCES.md §8). When disabled, `sync_latest_index` returns a
"disabled" status without touching the network; use `import_index_csv` for a
ToS-safe manual path.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import DataQualityIssue, IndexDaily
from nepse_sense.logging import logger
from nepse_sense.schemas.index import SOURCE_NAME, IndexRow, Issue
from nepse_sense.sources.adapters.merolagani_index import validate_rows

DISABLED_DETAIL = "ENABLE_MEROLAGANI=false; see docs/DATA_SOURCES.md §8"


def upsert_rows(db, rows: list[IndexRow]) -> int:
    """Idempotent insert of index rows keyed on (index_name, day, source).

    session.merge() only keys on the primary key, so we look up the unique
    constraint explicitly and update in place when the row already exists.
    """
    count = 0
    now = datetime.utcnow()
    for r in rows:
        existing = (
            db.query(IndexDaily)
            .filter(
                IndexDaily.index_name == r.index_name,
                IndexDaily.day == r.day,
                IndexDaily.source == r.source,
            )
            .first()
        )
        if existing is None:
            db.add(
                IndexDaily(
                    index_name=r.index_name,
                    day=r.day,
                    value=r.value,
                    change=r.change,
                    pct_change=r.pct_change,
                    source=r.source,
                    fetched_at=now,
                )
            )
        else:
            existing.value = r.value
            existing.change = r.change
            existing.pct_change = r.pct_change
            existing.fetched_at = now
        count += 1
    db.commit()
    return count


def record_index_issues(
    db, issues: list[Issue], index_name: str, source: str = SOURCE_NAME
) -> int:
    """Persist critical index issues to data_quality_issues (resolved=False)."""
    count = 0
    for i in issues:
        if i.severity != "critical":
            continue
        db.add(
            DataQualityIssue(
                symbol=index_name,  # index name stands in for the symbol column
                date=i.day,
                issue_type=i.code,
                severity=i.severity,
                description=i.detail,
                source=source,
                resolved=False,
            )
        )
        count += 1
    db.commit()
    return count


def sync_latest_index(source=None, db=None, index_name: str = "NEPSE") -> dict:
    """Fetch the latest index slice, validate, and upsert. Idempotent.

    Returns a summary dict: {"status", "detail", "upserted", "issues", "as_of"}.
    Does no network I/O when the source is disabled.
    """
    owns_db = db is None
    db = db or SessionLocal()
    try:
        if source is None:
            from nepse_sense.sources.factory import SourceFactory

            source = SourceFactory.get_index_source()
        if source is None:
            return {"status": "disabled", "detail": DISABLED_DETAIL, "upserted": 0, "issues": 0}
        try:
            rows = source.fetch_latest(index_name)
        except Exception as e:  # SourceError / network
            logger.warning(f"Index fetch failed: {e}")
            return {"status": "error", "detail": str(e), "upserted": 0, "issues": 0}
        if not rows:
            return {"status": "error", "detail": "no rows parsed", "upserted": 0, "issues": 0}

        issues = validate_rows(rows)
        n = upsert_rows(db, rows)
        ni = record_index_issues(db, issues, index_name, rows[0].source)
        as_of = max(r.day for r in rows)
        return {
            "status": "ok",
            "detail": f"{n} rows upserted, {ni} critical issues",
            "upserted": n,
            "issues": ni,
            "as_of": as_of,
        }
    finally:
        if owns_db:
            db.close()


def load_index_rows(
    db, index_name: str = "NEPSE", source: str | None = None, limit: int | None = None
) -> list[IndexRow]:
    """Load stored index rows (ascending by day) as IndexRow objects."""
    q = db.query(IndexDaily).filter(IndexDaily.index_name == index_name)
    if source:
        q = q.filter(IndexDaily.source == source)
    q = q.order_by(IndexDaily.day)
    if limit:
        q = q.limit(limit)
    return [
        IndexRow(
            index_name=r.index_name,
            day=r.day,
            value=r.value,
            change=r.change or 0.0,
            pct_change=r.pct_change or 0.0,
            source=r.source,
        )
        for r in q.all()
    ]


def latest_index_row(db, index_name: str = "NEPSE", source: str | None = None):
    q = db.query(IndexDaily).filter(IndexDaily.index_name == index_name)
    if source:
        q = q.filter(IndexDaily.source == source)
    return q.order_by(IndexDaily.day.desc()).first()


def import_index_csv(
    db,
    file_path: str | Path,
    index_name: str = "NEPSE",
    source: str = "csv",
) -> int:
    """Import index history from a CSV (ToS-safe manual path).

    Expected columns: date, value  (optional: change, pct_change). Missing
    change/pct are computed from consecutive rows. Date accepts %Y-%m-%d or
    %Y/%m/%d.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    def _parse_date(s: str):
        s = s.strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Unparsable date: {s}")

    parsed: list[tuple] = []
    with open(file_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            norm = {k.strip().lower(): v for k, v in row.items() if k}
            day = _parse_date(
                norm.get("date") or norm.get("day") or ""
            )
            value = float(norm.get("value") or norm.get("close") or norm.get("index_value"))
            change = norm.get("change", "")
            pct = norm.get("pct_change") or norm.get("percentage_change", "")
            parsed.append(
                (
                    day,
                    value,
                    float(change) if change not in ("", None) else None,
                    float(pct) if pct not in ("", None) else None,
                )
            )

    parsed.sort(key=lambda t: t[0])
    rows: list[IndexRow] = []
    prev_value = None
    for day, value, change, pct in parsed:
        if change is None:
            change = round(value - prev_value, 2) if prev_value is not None else 0.0
        if pct is None:
            pct = (
                round((value - prev_value) / prev_value * 100, 4)
                if prev_value
                else 0.0
            )
        rows.append(
            IndexRow(
                index_name=index_name,
                day=day,
                value=value,
                change=change,
                pct_change=pct,
                source=source,
            )
        )
        prev_value = value

    n = upsert_rows(db, rows)
    issues = validate_rows(rows)
    record_index_issues(db, issues, index_name, source)
    logger.info(f"Imported {n} index rows for {index_name} from {file_path}")
    return n
