# NEPSE Sense — Agent Build Guide

> **Put this file in an empty project folder, then tell the coding agent:**
> `Read NEPSE_SENSE_BUILD_GUIDE.md fully. Follow the Agent Protocol. Start with Milestone M1 only, then stop.`
> After each milestone finishes, reply: `Continue with the next milestone.`

---

## 0. AGENT PROTOCOL (read first, follow always)

You are a senior Python engineer building **NEPSE Sense** from scratch: an explainable stock scanner and Telegram bot for the Nepal Stock Exchange (NEPSE).

1. **Work one milestone at a time.** Do the milestone's tasks, run its acceptance checks, fix failures, commit, then **STOP** and print a short report (done / not done / assumptions / next milestone). Do not start the next milestone until told to.
2. **Maintain `PROGRESS.md`** in the repo root. At the start of every session, read it. At the end of every milestone, update it with: milestone status, files created, test results, open issues, assumptions.
3. **Do not ask questions** unless truly blocked. Make sensible assumptions and record them in `docs/ASSUMPTIONS.md`.
4. **Run `pytest` and `ruff check` before every commit.** Never commit failing tests. Commit message format: `M3: validation layer + canonical prices`.
5. **Never guess.** Do not invent API endpoints, schemas, rates, or data. Inspect real docs/repos if network is available; otherwise build against fixtures and mark the adapter `UNVERIFIED against live API`.
6. **Keep scope tight.** If something is not listed for the current milestone, don't build it. If you think something is missing, note it in `PROGRESS.md` under "Suggestions".
7. If the context gets long or you lose track, re-read this file's Sections 1–4 and `PROGRESS.md` before continuing.

---

## 1. PRODUCT GOAL

A personal, free-to-run tool that:

1. Ingests NEPSE daily price data from free sources and **validates** it.
2. Computes technical indicators and fundamentals-based filters for every listed stock.
3. Produces ranked, explainable **BUY WATCH / BUY CANDIDATE / SELL REVIEW / NEUTRAL** signals.
4. Delivers them via a Telegram bot with inline buttons and a scheduled post-close scan.

It must **never** present a signal as guaranteed profit, and **never** generate a fresh signal from stale, missing, or unvalidated data. It reports gaps honestly.

---

## 2. HARD RULES (non-negotiable)

- Never invent or guess data (EPS, broker data, news, prices). If unavailable, show **"Unavailable"** plus the reason.
- No fresh signals if: latest data is older than the last expected NEPSE trading day, validation failed, or the symbol has fewer than the required history bars.
- No hardcoded secrets. Use `.env` + `pydantic-settings`. Provide `.env.example`.
- Be a polite client: custom User-Agent, timeouts, retries with exponential backoff, rate limiting, local caching of raw responses.
- Check robots.txt/terms before scraping any website. If programmatic access is not clearly permitted, leave that adapter **DISABLED by default** and document why.
- Every user-facing signal message must include: **reasons, data date/timestamp, data source(s), and the warning "Educational analysis, not financial advice."**
- All messages must label experimental or unverified data clearly.

---

## 3. TECH STACK

- Python 3.12+, `uv` or `venv` + pip (`pyproject.toml` or `requirements.txt`)
- `pandas`, `numpy`. **Implement indicators yourself** (no pandas-ta): RSI (Wilder), MACD 12/26/9, EMA 20/50, ATR14, relative volume, pivot-based support/resistance.
- `httpx` + `tenacity` (retries), `BeautifulSoup4` (only for permitted HTML sources)
- SQLAlchemy 2.x + SQLite (WAL mode). Alembic or a simple versioned schema init.
- `python-telegram-bot` v21+ (async), **long polling** (no webhook, no public server)
- `APScheduler`, timezone `Asia/Kathmandu`
- `pydantic`, `pydantic-settings`, `loguru` or stdlib logging (rotating file)
- `matplotlib` (charts), `typer` (CLI), `pytest`, `ruff`
- **FastAPI is OUT OF SCOPE for v1.** Keep a clean `services/` layer so an API can be added later.

---

## 4. DATA SOURCES

Define abstract interfaces:

- `PriceSource`: `fetch_symbols()`, `fetch_history(symbol, start, end)`, `fetch_daily_snapshot(date)`
- `NoticeSource`: `fetch_notices(since)`
- `BrokerDataSource`: stub that always returns "Unavailable"

Adapters return normalized pydantic models.

| # | Source | Role | Default |
|---|--------|------|---------|
| 1 | **ShareSansar historical archive API** — docs at https://omitnomis.github.io/ (historical OHLCV, all-stock daily snapshots, symbol list, market recap). Unofficial. | PRIMARY | Enabled |
| 2 | **NEPSE Data daily archive** (GitHub repo referenced by the project above). Check license/redistribution terms. | SECONDARY, cross-validation + bulk backfill | Enabled |
| 3 | **NEPSEAPI** unofficial live-data experiment (GitHub). Personal/educational use only. | OPTIONAL | **Disabled** (`ENABLE_EXPERIMENTAL_LIVE=false`). Any alert from it labelled `EXPERIMENTAL / UNVERIFIED`, never the sole basis for an alert. |
| 4 | **nepalstock.com** and **sebon.gov.np** (notices, corporate actions) | `NoticeSource` | **Disabled** unless programmatic access is clearly permitted |
| 5 | **CSV import** (`python -m nepse_sense import-csv file.csv`) for OHLCV and fundamentals | Fallback if all web sources break | Always available |
| 6 | **Manual events**: `data/events.csv` importer + `/addevent` admin command | Bonus/dividend/rights/book-closure entry | Always available |

Record real findings (endpoints, schemas, rate limits, licenses, verified/unverified status) in `docs/DATA_SOURCES.md`.

**No network access?** Build against fixtures in `tests/fixtures/` that mimic the documented schema, and flag adapters as unverified.

### Data-quality layer
For each symbol/day compare close and volume between primary and secondary sources. Configurable tolerances (default **1% price, 10% volume**). Detect:
- missing trading days (NEPSE trades **Sunday–Thursday**, Asia/Kathmandu, closes ~15:00; holidays from `config/holidays.csv`)
- duplicates, zero/negative prices, `high < low`, close outside `[low, high]`
- suspicious jumps **> 10%** daily (NEPSE circuit limit is ±10%; larger implies unadjusted bonus/rights/split)

Store in `data_quality_issues`. Symbols with unresolved **critical** issues are excluded from signals and listed in `/status`.

### Corporate actions
Store **raw** prices and an **adjusted** series (adjust for bonus/rights/dividend when event data exists). If event data is missing, **flag suspected unadjusted gaps** instead of silently computing indicators across them.

---

## 5. DATABASE (SQLite)

Tables:
`symbols`, `prices_daily` (unique symbol+date+source), `prices_canonical` (validated merged row with provenance), `indicators_daily`, `fundamentals`, `events`, `news`, `signals` (symbol, date, type, score, reasons JSON, risk_flags JSON, data_asof, sources, created_at), `signal_outcomes`, `users` (telegram_id, settings JSON), `watchlist`, `portfolio_holdings`, `alerts_sent` (dedupe), `source_health`, `scan_runs`, `data_quality_issues`.

---

## 6. ANALYSIS ENGINE SPEC

**Technical (on adjusted closes where available):**
EMA20, EMA50, trend state, RSI14, RSI reversal (cross up from <30 / cross down from >70; simple divergence), MACD line/signal/histogram + crossovers, relative volume (vs 20-day avg), ATR14, 52-week high/low proximity, support/resistance as **zones** from clustered swing pivots (with touch counts), liquidity filter (min avg turnover, configurable).

**Fundamentals (only if data exists):**
EPS, P/E, book value, P/B, sector-relative P/E, and a transparent 0–100 quality score with visible breakdown. Missing fundamentals → "Unavailable" and the stock is **capped at BUY WATCH** (configurable).

**Signal scoring:**
Rule-based, weights in `config/signals.yaml`. Each rule adds points **and** a human-readable reason. Output: category, score 0–100, confidence tier (from data completeness + indicator agreement), key levels (nearest support/resistance, ATR-based invalidation level), risk flags (low liquidity, near resistance, extended above EMA, unadjusted gap, stale fundamentals, circuit-limit move).

**Market overview:**
NEPSE index trend (if available), advancers/decliners, total turnover, sector strength ranking, regime label (Bullish/Mixed/Bearish) with rules shown.

**Bulk/broker data:** not in v1 scope. `/bulk` = volume-anomaly detector (relative volume + price move) labelled *"unusual activity, not confirmed bulk deals"*. `/brokers` replies that broker data is unavailable.

---

## 7. BACKTESTING SPEC

Custom event-driven daily backtester on canonical data:
- Enter at **next day's open** after a signal (no lookahead)
- Configurable holding period, ATR stop, target
- NEPSE costs fully configurable (broker commission tiers, SEBON fee, DP charge, capital gains tax; sensible defaults marked **"verify current rates"**), slippage, min lot
- Walk-forward / out-of-sample split (train vs unseen test)
- Report: trades, win rate, avg return, max drawdown, profit factor, vs buy-and-hold
- Results stored and shown via `/report`
- **Include a test proving no lookahead bias**

---

## 8. TELEGRAM BOT SPEC

- Single-owner: `ALLOWED_TELEGRAM_IDS` whitelist in `.env`; ignore everyone else.
- Inline keyboards, message editing, HTML parse mode with proper escaping, pagination for long lists, mobile-friendly concise text.

**Commands:**
`/start` `/help` `/buy` `/sell` `/top` `/stock SYMBOL` `/market` `/news` `/events` `/bulk` `/watchlist` `/add SYMBOL` `/remove SYMBOL` `/alerts` `/settings` `/status` `/report`
Extras: `/support SYMBOL` `/fundamental SYMBOL` `/compare A B` `/risk SYMBOL PRICE` `/chart SYMBOL` `/portfolio` `/brokers` (honest "unavailable") `/addevent` (admin).

**`/stock SYMBOL`** shows: last close + change, data date + sources, technical setup (Bullish/Mixed/Bearish), indicators, support/resistance zones, fundamental score + breakdown or "Unavailable", broker activity "Unavailable", latest news/events, signal + reasons + risk flags. Buttons: `[Technical] [Fundamentals] [News] [Chart] [Alert on/off] [Add/Remove watchlist]`. Symbols are case-insensitive with fuzzy "did you mean" suggestions.

**`/chart SYMBOL`**: matplotlib PNG (candles or line, EMA20/50, S/R zones, volume, RSI/MACD panels) sent as photo.

**`/status`**: per-source health, last successful ingest per source, last scan time, symbols scanned vs excluded (with reasons), open data-quality issues, scheduler state.

**Alerts:** daily post-close digest (default 15:45 NPT, Sun–Thu, skip holidays): top candidates + watchlist changes + new events. Deduplicate within N days unless score/category changed materially. Per-user settings: alerts on/off, min score, signal types, quiet mode, max items. If the scan couldn't run on fresh data, send **one** clear "No signals today: data stale/unavailable" message.

---

## 9. SCHEDULED JOBS

- **15:30 NPT Sun–Thu:** ingest → validate → canonicalize
- **15:45:** indicators + signals + digest
- **Weekly:** full gap re-sync/backfill check
- **Every 15 min:** cheap source health ping
- **Optional (flag):** experimental intraday live job

All jobs idempotent and safe to re-run; log to `scan_runs`.

---

## 10. CLI

`python -m nepse_sense init-db | backfill --years 5 | ingest | scan | import-csv | run-bot | backtest | doctor`

`doctor` checks env vars, DB, network reachability per source, and prints a pass/fail table.
`run-bot --demo` seeds synthetic data so everything works with no network.

---

## 11. PROJECT STRUCTURE

```
nepse_sense/
  config/  db/  sources/  validation/  indicators/  signals/
  fundamentals/  events/  backtest/  bot/  jobs/  services/  cli.py
tests/ (with fixtures/)
docs/  DATA_SOURCES.md  ASSUMPTIONS.md  SIGNALS.md  RUNBOOK.md
config/  signals.yaml  holidays.csv
README.md  PROGRESS.md  Makefile  .env.example  .gitignore  .pre-commit-config.yaml
```

README must cover: macOS setup in <10 minutes, creating a bot with @BotFather, finding your Telegram ID, running, and keeping it alive with `launchd` or `tmux`.

---

## 12. TESTING & QUALITY (applies to every milestone)

- Indicators tested against hand-computed/reference values
- Validators tested with deliberately broken data
- Signal rules tested with synthetic series
- Stale-data gating test
- Message formatting/escaping tests
- Bot handlers tested with mocked Telegram updates
- Adapters tested with recorded fixtures; optional `-m live` marker for real-network tests
- Type hints throughout, ruff clean, structured logging, no bare `except`, graceful degradation when a source fails

---

# MILESTONES

Each milestone ends with a **STOP GATE**. Do not proceed past it without being told.

## M1 — Scaffolding, config, DB, CLI, doctor
**Tasks**
- [ ] Repo layout, `pyproject.toml`/requirements, Makefile (`setup`, `test`, `lint`, `run`), `.gitignore`, `.env.example`, pre-commit
- [ ] `pydantic-settings` config; logging setup
- [ ] SQLAlchemy models for all tables in Section 5; `init-db`
- [ ] Typer CLI skeleton with all commands from Section 10 (stubs OK except `init-db`, `doctor`)
- [ ] `doctor` command with pass/fail table
- [ ] `PROGRESS.md`, `docs/ASSUMPTIONS.md` created

**Acceptance:** `make setup && make test && make lint` pass; `init-db` creates DB; `doctor` runs.
**STOP GATE → report, then wait.**

## M2 — Source adapters, CSV import, caching, source docs
**Tasks**
- [ ] `PriceSource`, `NoticeSource`, `BrokerDataSource` interfaces + pydantic models
- [ ] ShareSansar adapter (from real docs), NEPSE Data archive adapter, NEPSEAPI adapter (disabled by default), notice adapters (disabled by default)
- [ ] Raw-response cache, rate limiter, retries, custom User-Agent
- [ ] CSV import for OHLCV and fundamentals; `data/events.csv` importer
- [ ] `docs/DATA_SOURCES.md` with real findings, license notes, verified/unverified status
- [ ] Fixture-based adapter tests

**Acceptance:** adapters pass fixture tests; CSV import loads sample data into `prices_daily`; docs written.
**STOP GATE.**

## M3 — Validation, canonical prices, corporate actions, source health
**Tasks**
- [ ] Trading calendar (Sun–Thu, holidays CSV, close time)
- [ ] All checks from "Data-quality layer"; write to `data_quality_issues`
- [ ] Cross-source comparison with configurable tolerances
- [ ] `prices_canonical` builder with provenance
- [ ] Adjusted price series from events; unadjusted-gap flagging
- [ ] `source_health` recording
- [ ] Tests with deliberately broken data

**Acceptance:** each issue type is detected in tests; critical-issue symbols are marked excluded.
**STOP GATE.**

## M4 — Indicators and support/resistance
**Tasks**
- [ ] EMA, RSI (Wilder), MACD, ATR, relative volume, 52-week proximity, RSI reversal/divergence
- [ ] Swing-pivot clustering into S/R zones with touch counts
- [ ] Liquidity filter
- [ ] Persist to `indicators_daily`
- [ ] Reference-value tests for every formula

**Acceptance:** all indicator tests pass against reference values.
**STOP GATE.**

## M5 — Fundamentals and signal engine
**Tasks**
- [ ] Fundamentals model: EPS, P/E, book value, P/B, sector-relative P/E, 0–100 score with breakdown
- [ ] `config/signals.yaml` weights; rule engine producing score + reasons
- [ ] Categories, confidence tier, key levels, risk flags
- [ ] Stale-data / insufficient-history gating
- [ ] `docs/SIGNALS.md` documenting every rule
- [ ] Synthetic-series tests per rule; gating test

**Acceptance:** stale or invalid-data symbols never produce signals; missing fundamentals cap at BUY WATCH.
**STOP GATE.**

## M6 — Telegram bot
**Tasks**
- [ ] Whitelist middleware, HTML-safe formatting, pagination
- [ ] All commands in Section 8 with inline buttons and message editing
- [ ] `/stock` full report with fuzzy symbol matching
- [ ] `/chart` matplotlib rendering
- [ ] Watchlist, settings, portfolio (manual holdings + P/L), `/addevent`
- [ ] `--demo` synthetic data seeding
- [ ] Mocked-update handler tests

**Acceptance:** `run-bot --demo` works and every command responds sensibly.
**STOP GATE.**

## M7 — Scheduler, digest, dedupe, status
**Tasks**
- [ ] APScheduler jobs from Section 9 (idempotent, `scan_runs` logging)
- [ ] Digest builder, dedupe via `alerts_sent`, per-user settings
- [ ] Single "no signals: data stale" message path
- [ ] Full `/status`
- [ ] Tests for dedupe and stale gating

**Acceptance:** re-running a job doesn't duplicate alerts; stale data yields exactly one clear message.
**STOP GATE.**

## M8 — Backtester and /report
**Tasks**
- [ ] Event-driven backtester per Section 7
- [ ] Configurable NEPSE costs (marked "verify current rates"), slippage, min lot
- [ ] Walk-forward split; metrics; store results
- [ ] `/report` command and `backtest` CLI
- [ ] **No-lookahead test**

**Acceptance:** lookahead test passes; report shows in-sample vs out-of-sample separately.
**STOP GATE.**

## M9 — Events, news, polish, final demo
**Tasks**
- [ ] Events from manual/CSV and any permitted sources; `/events` list by type and date
- [ ] `/news` ranked by simple impact rules (rights/bonus/dividend/merger/book-closure/AGM/deadline)
- [ ] README polish, RUNBOOK, launchd/tmux instructions
- [ ] Final end-to-end `--demo` run
- [ ] Final summary printed

**Acceptance (Definition of Done):**
- `make setup && make test` passes on a clean machine
- `python -m nepse_sense run-bot --demo` works, every command responds
- With real data configured, a post-close scan produces ranked, explained signals and refuses to signal on stale data
- Docs state which sources are verified vs unverified and every limitation

**Final output:** summary of what was built, what is unverified, known limitations, and the **5 most valuable next steps**.
