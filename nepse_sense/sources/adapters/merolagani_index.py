"""MeroLagani index adapter for NEPSE Sense.

Fetches NEPSE / sector index history from https://merolagani.com/Indices.aspx,
validates it, and turns it into a market-regime summary for the bot's /market
command. Storage is handled separately (SQLAlchemy `IndexDaily` upserts in
`nepse_sense.indexing.service`); this module only parses/fetches/labels.

STATUS
- Table parsing, validation, regime logic and message formatting are tested
  against a fixture.
- Fetching the latest page (GET) matches what the page serves today.
- Paging back through history (ASP.NET postback) is UNVERIFIED against the live
  site. If it fails, the code stops cleanly and reports why; use CSV import.
- Automated access is PROHIBITED by the site's Terms of Service (see
  docs/DATA_SOURCES.md §8). Keep ENABLE_MEROLAGANI=false (the default) so the
  fetch paths never run against the live site.

Design rules (same as the rest of NEPSE Sense)
- Never invent data. If rows are stale/insufficient the regime is "Unavailable".
- Polite client: identifying User-Agent, timeout, minimum delay between
  requests, backoff on errors, raw-HTML cache, circuit breaker.
- No hardcoded cookies. Session state is handled by the HTTP client.
- Logic below is kept verbatim from the provided reference adapter; only the
  storage layer and the trading-day helper were rewired to project modules.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from bs4 import BeautifulSoup

from nepse_sense.config import settings
from nepse_sense.schemas.index import IndexRow, Issue, MarketRegime
from nepse_sense.sources.base import IndexSource

log = logging.getLogger("nepse_sense.merolagani_index")

BASE_URL = "https://merolagani.com/Indices.aspx"
# Descriptive UA: the site's ToS disallows automated collection; identify the
# caller honestly as a personal, non-commercial project.
USER_AGENT = "NepseSense/0.1 (personal student project; not for redistribution)"
MIN_DELAY_SECONDS = 2.5  # politeness gap between requests

# ASP.NET form field names seen on the page.
F_INDEX = "ctl00$ContentPlaceHolder1$ddlIndexFilter"
F_PAGE1 = "ctl00$ContentPlaceHolder1$PagerControl1$hdnCurrentPage"
F_PAGE1_BTN = "ctl00$ContentPlaceHolder1$PagerControl1$btnPaging"
F_PAGE2 = "ctl00$ContentPlaceHolder1$PagerControl2$hdnCurrentPage"


class SourceError(RuntimeError):
    """Raised when the source cannot be fetched or parsed."""


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------
def _num(text: str) -> float:
    cleaned = text.replace(",", "").replace("%", "").strip()
    if not cleaned:
        raise ValueError("empty number")
    return float(cleaned)


def _find_index_table(soup: BeautifulSoup):
    """Find the table by its headers, not by CSS classes (more robust)."""
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if "Index Value" in headers and any(h.startswith("Date") for h in headers):
            return table
    return None


def parse_index_table(page_html: str, index_name: str = "NEPSE") -> list[IndexRow]:
    """Parse one page of the Indices table into IndexRow objects."""
    soup = BeautifulSoup(page_html, "html.parser")
    table = _find_index_table(soup)
    if table is None:
        raise SourceError("Index table not found (page layout may have changed)")

    headers = [th.get_text(strip=True) for th in table.find_all("th")]
    col = {h: i for i, h in enumerate(headers)}
    date_col = next(i for h, i in col.items() if h.startswith("Date"))
    try:
        val_col = col["Index Value"]
        chg_col = col["Absolute Change"]
        pct_col = col["Percentage Change"]
    except KeyError as exc:
        raise SourceError(f"Missing expected column: {exc}") from exc

    rows: list[IndexRow] = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < len(headers):
            continue
        try:
            rows.append(
                IndexRow(
                    index_name=index_name,
                    day=datetime.strptime(cells[date_col], "%Y/%m/%d").date(),
                    value=_num(cells[val_col]),
                    change=_num(cells[chg_col]),
                    pct_change=_num(cells[pct_col]),
                )
            )
        except ValueError as exc:
            log.warning("Skipping unparsable row %s: %s", cells, exc)
    if not rows:
        raise SourceError("Index table found but no rows could be parsed")
    return rows


def parse_index_options(page_html: str) -> dict[str, str]:
    """Return {index display name: option value} from the index dropdown."""
    soup = BeautifulSoup(page_html, "html.parser")
    select = soup.find("select", attrs={"name": F_INDEX})
    if select is None:
        return {}
    return {
        opt.get_text(strip=True): opt.get("value", "")
        for opt in select.find_all("option")
    }


def parse_total_pages(page_html: str) -> int | None:
    match = re.search(r"Total pages:\s*(\d+)", page_html)
    return int(match.group(1)) if match else None


def _hidden_fields(page_html: str) -> dict[str, str]:
    soup = BeautifulSoup(page_html, "html.parser")
    return {
        inp["name"]: inp.get("value", "")
        for inp in soup.find_all("input", attrs={"type": "hidden"})
        if inp.get("name")
    }


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def validate_rows(
    rows: Sequence[IndexRow],
    max_daily_move_pct: float = 10.0,
    abs_tol: float = 0.06,
    pct_tol: float = 0.03,
) -> list[Issue]:
    """Check internal consistency. Critical issues should block use of the row."""
    issues: list[Issue] = []
    by_day: dict[date, IndexRow] = {}
    for r in rows:
        if r.day in by_day:
            issues.append(Issue(r.day, "critical", "duplicate", "Duplicate date"))
        by_day[r.day] = r
        if r.value <= 0:
            issues.append(Issue(r.day, "critical", "non_positive", f"value={r.value}"))
        if abs(r.pct_change) > max_daily_move_pct:
            issues.append(
                Issue(r.day, "warning", "big_move", f"{r.pct_change}% exceeds limit")
            )

    ordered = sorted(by_day.values(), key=lambda r: r.day)
    for prev, cur in zip(ordered, ordered[1:], strict=False):
        expected = round(cur.value - prev.value, 2)
        if abs(expected - cur.change) > abs_tol:
            issues.append(
                Issue(
                    cur.day,
                    "critical",
                    "change_mismatch",
                    f"reported change {cur.change} vs computed {expected}",
                )
            )
        elif prev.value > 0:
            expected_pct = (cur.value - prev.value) / prev.value * 100
            if abs(expected_pct - cur.pct_change) > pct_tol:
                issues.append(
                    Issue(
                        cur.day,
                        "warning",
                        "pct_mismatch",
                        f"reported {cur.pct_change}% vs computed {expected_pct:.2f}%",
                    )
                )
    return issues


# --------------------------------------------------------------------------
# Fetching (polite client; own circuit breaker + throttle + retry + cache)
# --------------------------------------------------------------------------
class MeroLaganiIndexSource(IndexSource):
    def __init__(
        self,
        cache_dir: str | Path | None = None,
        min_delay: float = MIN_DELAY_SECONDS,
        timeout: float | None = None,
        max_retries: int | None = None,
        failure_threshold: int = 4,
        cooldown_minutes: int = 30,
        client=None,
    ) -> None:
        self.cache_dir = Path(cache_dir or settings.cache_dir / "merolagani")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_delay = min_delay
        self.max_retries = max_retries or settings.request_retries
        self.failure_threshold = failure_threshold
        from datetime import timedelta

        self.cooldown = timedelta(minutes=cooldown_minutes)
        self._failures = 0
        self._disabled_until: datetime | None = None
        self._last_request = 0.0
        if client is None:
            import httpx  # imported lazily so parsing/tests don't need it

            client = httpx.Client(
                headers={"User-Agent": USER_AGENT},
                timeout=timeout or settings.request_timeout,
                follow_redirects=True,
            )
        self.client = client

    # -- plumbing ---------------------------------------------------------
    def _check_circuit(self) -> None:
        if self._disabled_until and datetime.now() < self._disabled_until:
            raise SourceError(f"Circuit open until {self._disabled_until:%H:%M}")

    def _throttle(self) -> None:
        wait = self.min_delay - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _request(self, method: str, data: dict | None = None) -> str:
        self._check_circuit()
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                resp = self.client.request(method, BASE_URL, data=data)
                if resp.status_code == 429 or resp.status_code >= 500:
                    retry_after = float(resp.headers.get("Retry-After", 0) or 0)
                    time.sleep(max(retry_after, 2**attempt * 2))
                    last_exc = SourceError(f"HTTP {resp.status_code}")
                    continue
                resp.raise_for_status()
                self._failures = 0
                text = resp.text
                self._cache(text, method, data)
                return text
            except Exception as exc:  # network errors vary by client
                last_exc = exc
                time.sleep(2**attempt * 2)
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._disabled_until = datetime.now() + self.cooldown
        raise SourceError(f"Request failed: {last_exc}")

    def _cache(self, text: str, method: str, data: dict | None) -> None:
        key = hashlib.sha1(  # noqa: S324 - cache key only, not security-sensitive
            f"{method}{sorted((data or {}).items())}".encode()
        ).hexdigest()[:12]
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        (self.cache_dir / f"{stamp}_{key}.html").write_text(text, encoding="utf-8")

    # -- public API (IndexSource) ----------------------------------------
    def fetch_latest(self, index_name: str = "NEPSE") -> list[IndexRow]:
        """Latest ~100 rows of the default (NEPSE) index. One cheap GET."""
        return parse_index_table(self._request("GET"), index_name)

    def list_indices(self) -> dict[str, str]:
        return parse_index_options(self._request("GET"))

    def backfill(
        self,
        index_name: str = "NEPSE",
        index_value: str | None = None,
        max_pages: int = 30,
        stop_before: date | None = None,
    ) -> list[IndexRow]:
        """Walk back through history page by page (UNVERIFIED postback).

        Stops when: max_pages reached, the oldest row is before `stop_before`,
        the site reports no more pages, or a page adds no new dates.
        """
        first_html = self._request("GET")
        all_rows = parse_index_table(first_html, index_name)
        total = parse_total_pages(first_html) or 1
        hidden = _hidden_fields(first_html)
        seen = {r.day for r in all_rows}

        for page in range(2, min(total, max_pages) + 1):
            if stop_before and min(seen) <= stop_before:
                break
            form = dict(hidden)
            if index_value is not None:
                form[F_INDEX] = index_value
            form[F_PAGE1] = str(page)
            form[F_PAGE1_BTN] = ""
            form[F_PAGE2] = str(page)
            try:
                page_html = self._request("POST", form)
                rows = parse_index_table(page_html, index_name)
            except SourceError as exc:
                log.error("Backfill stopped at page %d: %s", page, exc)
                break
            new = [r for r in rows if r.day not in seen]
            if not new:
                log.error("Page %d added no new dates; paging may not work", page)
                break
            all_rows.extend(new)
            seen.update(r.day for r in new)
            hidden = _hidden_fields(page_html) or hidden
        return all_rows

    def fetch_history(
        self, index_name: str = "NEPSE", max_pages: int = 30
    ) -> list[IndexRow]:
        """IndexSource.fetch_history -> backfill."""
        return self.backfill(index_name=index_name, max_pages=max_pages)


# --------------------------------------------------------------------------
# Market regime for /market
# --------------------------------------------------------------------------
def ema(values: Sequence[float], span: int) -> list[float]:
    alpha = 2 / (span + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out


def compute_regime(
    rows: Sequence[IndexRow],
    expected_last_day: date | None = None,
    min_rows: int = 60,
) -> MarketRegime:
    """Rule-based trend label. Refuses to label stale or short data."""
    if len(rows) < min_rows:
        return MarketRegime(
            "Unavailable",
            None,
            None,
            None,
            reasons=[f"Only {len(rows)} index rows; need at least {min_rows}."],
        )
    ordered = sorted(rows, key=lambda r: r.day)
    last = ordered[-1]

    if expected_last_day and last.day < expected_last_day:
        return MarketRegime(
            "Unavailable",
            last.day,
            last.value,
            last.pct_change,
            reasons=[
                f"Latest index data is {last.day}, expected {expected_last_day}."
            ],
            stale=True,
        )

    closes = [r.value for r in ordered]
    e20, e50 = ema(closes, 20), ema(closes, 50)
    px, a, b = closes[-1], e20[-1], e50[-1]
    b_prev = e50[-6]
    rising, falling = b > b_prev, b < b_prev
    ret20 = (px / closes[-21] - 1) * 100

    reasons = [
        f"Index {px:,.2f} vs EMA20 {a:,.2f} and EMA50 {b:,.2f}.",
        f"EMA50 is {'rising' if rising else 'falling' if falling else 'flat'} over 5 days.",
        f"20-session change: {ret20:+.1f}%.",
    ]
    if px > a > b and rising:
        label = "Bullish"
    elif px < a < b and falling:
        label = "Bearish"
    else:
        label = "Mixed"

    warnings = [
        f"{i.code} on {i.day}: {i.detail}"
        for i in validate_rows(ordered[-60:])
        if i.severity == "critical"
    ]
    return MarketRegime(label, last.day, last.value, last.pct_change, reasons, warnings)


_EMOJI = {"Bullish": "🟢", "Bearish": "🔴", "Mixed": "🟡", "Unavailable": "⚪"}


def format_market_message(regime: MarketRegime) -> str:
    """Telegram HTML message for /market (all dynamic text is escaped)."""
    import html as html_lib

    esc = html_lib.escape
    lines = [f"{_EMOJI[regime.label]} <b>Market regime: {esc(regime.label)}</b>"]
    if regime.last_value is not None and regime.as_of is not None:
        lines.append(
            f"NEPSE index: <b>{regime.last_value:,.2f}</b> "
            f"({regime.day_change_pct:+.2f}%)  |  as of {regime.as_of}"
        )
    for r in regime.reasons:
        lines.append(f"• {esc(r)}")
    if regime.stale:
        lines.append("⚠️ Data is stale, so no fresh regime is shown.")
    for w in regime.warnings:
        lines.append(f"⚠️ Data check: {esc(w)}")
    lines.append(f"Source: {esc(regime.source)} (unofficial)")
    lines.append("<i>Educational analysis, not financial advice.</i>")
    return "\n".join(lines)
