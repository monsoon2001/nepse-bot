# NEPSE Sense - Progress

## Current Status
- **Active Milestone:** M9 — Documentation, production hardening, final polish (Completed)
- **Overall:** 9/9 milestones completed

## M1-M8 Completed

## M9 — Documentation, production hardening, final polish
- **Status:** Completed
- **Started:** 2026-10-17
- **Completed:** 2026-10-17

### Completed
- [x] README polished (features, setup, usage, bot commands, demo mode, config, data sources, disclaimer)
- [x] RUNBOOK expanded (launchd plist, backup/restore, rebuild-from-scratch, troubleshooting table, health checks, logs)
- [x] End-to-end smoke test: init-db -> import CSV -> scan -> backtest -> doctor (all work)
- [x] Wired scan CLI to full pipeline (canonicalize -> indicators -> signals) via services/scanner.py
- [x] pyproject dependencies synced (added PyYAML, pytest-asyncio)
- [x] Consistent disclaimers and "verify current NEPSE/SEBON rates" markers

### Test Results
- 47 passed, ruff clean

## M10 — News delivery (briefings, /news, urgent alerts)
- **Status:** Completed
- **Started:** 2026-10-18
- **Completed:** 2026-10-18

### Delivered
- [x] **10:00 NPT pre-market briefing** (Sun–Thu, holiday-aware): today's events/deadlines + news since last successful briefing (cursor in `news_briefings` table), impact-ranked, watchlist first, max 10 items, headline/source/published time/link only (no article text). Explicit messages when no permitted source is enabled or all sources failed.
- [x] **`/news` command**: since last market close; `/news N` (N clamped ≤7); `/news SYMBOL` filter; paginated with inline Prev/Next buttons (`news:page:<n>:<arg>`).
- [x] **Cross-source dedupe**: normalized headline + publication date key (`sha256`), second source recorded in `alt_sources`; in-batch + DB-level dedupe.
- [x] **Urgent watchlist alerts** (opt-in, default OFF, per-user `urgent_alerts`): during market hours (11:00–15:00 NPT, Sun–Thu) high-impact (≥60) watchlist news is pushed; deduped per user via `AlertSent`. Toggle button in `/profile`.
- [x] **robots.txt/RSS-only compliance** (`nepse_sense/news/robots.py`): runtime robots.txt check (404→permit, explicit Disallow→deny, error→conservative deny); HTML scraping never implemented; findings documented in `docs/DATA_SOURCES.md` §7 (verified 2026-10-18: OnlineKhabar RSS enabled by default; merolagani/ekantipur/setopati/nepalstock disabled — no permitted RSS).
- [x] Scheduler: `news_briefing` (10:00) + `urgent_news` (*/15, 11–14h) jobs; background scheduler now starts inside the bot process (`start_background_scheduler`) with a runtime bridge (`jobs/runtime.py`) binding the bot to the APScheduler threads.
- [x] Tests (`tests/test_news.py`, 18 tests): Thu→Sun gap window logic, N≤7 clamp, dedupe (normalization + alt_sources), no-source/all-failed/partial-failure messages, briefing delivery advances cursor only on success, symbol filter, urgent opt-in + market-hours gating + re-alert dedupe, ranking/cap.
- [x] Post-launch fixes (verified against live feeds): `normalize_headline` used the Bengali Unicode block (U+0980–09FF) instead of Devanagari (U+0900–097F) so every Nepali headline normalized to empty and was dropped — fixed + regression test; default feed switched to OnlineKhabar **business category** feed (main feed carries 0 market news); keyword rules expanded (राष्ट्र बैंक, सेयर/शेयर बजार, पुँजीबजार, बैंक/बैंकिङ, बीमा, लगानी, ऋण…); relevance gate now requires a real match (symbol/keyword/watchlist/event), not the base source weight — verified: 12/55 live business-feed items relevant, general news correctly excluded.

### Test Results
- 65 passed, ruff clean

## M11 — Quick stock lookup + upgraded stock card & charts
- **Status:** Completed
- **Started:** 2026-10-18
- **Completed:** 2026-10-18

### Delivered
- [x] **Plain-text & unknown-command lookup** (`nepse_sense/bot/lookup.py`): any non-command text or `/word` that matches a known symbol case-insensitively shows the full stock card; ticker-like typos get "Did you mean X?" suggestion buttons (`pick:SYMBOL`, difflib ≥0.6); greeting/stop words fall back to the help nudge. Symbol universe = distinct `PriceCanonical` symbols ∪ `symbols` master table.
- [x] **Enhanced stock card**: Price (last close, as-of date, sources), Technical (RSI with 🟢/🟡 state, EMA20, EMA50, ATR14, MACD line/signal), Signal summary + reasons + risk flags + disclaimer; when history is ≥10 but <50 bars, a note explains why no signal exists. Buttons: Chart, Technical, Fundamentals, News (symbol-filtered `/news`), per-symbol Alert on/off (muted symbols in `User.settings["muted_symbols"]`, upserts user row), Watchlist toggle (add/remove), Back.
- [x] **Chart upgraded to candlesticks** (`nepse_sense/bot/chart.py`, pure matplotlib, no new deps): candle bodies/wicks, EMA20/EMA50, S/R zones shaded from `IndicatorDaily.zones`, volume panel, RSI panel (30/70 lines), MACD panel (line/signal/histogram), title with symbol + as-of date. `render_chart` returns `(BytesIO, as_of_date)`; figure closed in `finally`; buffer closed after send — no temp files.
- [x] **Timeframe buttons** [3M][6M][1Y] on chart photos (`chart:SYMBOL:TF`, 90/180/365 bars): re-render off the event loop via `asyncio.to_thread` and **edit the photo in place** (`edit_message_media`) when the target message already has a photo, else send new; "Back to card" (`card:SYMBOL`) re-renders the report in place.
- [x] **Unavailable handling** (`symbol_status`): insufficient history (<10 bars), unresolved critical `DataQualityIssue`, missing data, or stale data (>3 expected trading days missed, holiday/weekend-aware via `TradingCalendar.is_trading_day`) → "⛔ Unavailable" card with the exact reason, no fake values, no chart button.
- [x] Tests (`tests/test_lookup.py`, 14 tests): exact + case-insensitive match, lowercase plain-text card, typo suggestions, unknown word nudge, unknown `/command` lookup, chart callback sends photo + timeframe keyboard, 3M timeframe edits photo in place (90 bars), critical-issue card shows Unavailable + no chart button, alert toggle persists `muted_symbols`.

### Test Results
- 80 passed, ruff clean

## M12 — Config-driven market clock + MeroLagani index adapter
- **Status:** Completed
- **Started:** 2026-10-18
- **Completed:** 2026-10-18

### Delivered
- [x] **Config-driven trading calendar** (`nepse_sense/clock.py::MarketClock` + `TRADING_DAYS`, `SESSION_OPEN`, `SESSION_CLOSE`, `DATA_GRACE_MINUTES`): replaces every hardcoded Sunday–Thursday assumption (6 scheduler cron strings + Python checks in `news/windows.py`, `news/briefing.py`, `signals/engine._is_stale`, `calendar/trading_calendar.py`). **Default flipped to Mon–Fri** (inferred from observed index dates) — flagged UNVERIFIED in `docs/ASSUMPTIONS.md`; set `TRADING_DAYS=sun,mon,tue,wed,thu` to restore the old calendar. `trading_days` accepts ints or day names. `/status` and `doctor` warn if stored prices disagree with `TRADING_DAYS`.
- [x] **`IndexSource` interface** added to `sources/base.py` (sync — the client is sync httpx with GET+POST paging and its consumers are sync); `IndexRow`/`Issue`/`MarketRegime` moved to `schemas/index.py`.
- [x] **MeroLagani index adapter** (`sources/adapters/merolagani_index.py`): parsing, validation, EMA/regime and message formatting kept **verbatim** from the provided reference; the polite client keeps its own circuit breaker + throttle + retry + raw-HTML cache. Backfill paging stays UNVERIFIED against the live site.
- [x] **`IndexDaily` model** (`index_daily`, unique on `index_name+day+source`) + `nepse_sense/indexing/service.py` (idempotent upserts keyed on the unique constraint; critical validation issues → `data_quality_issues`).
- [x] **Disabled by default** (`ENABLE_MEROLAGANI=false`): `docs/DATA_SOURCES.md` §8 records the finding that the site's Terms (§3, `Disclaimer.aspx`) prohibit automated collection "regardless of … purpose" and that `robots.txt` 404s, so no live fetch is performed. ToS-safe path = `import-index-csv`. (No live request was made against MeroLagani.)
- [x] **CLI**: `index-sync` (respects the disable flag, points to CSV import when off) and `import-index-csv <file> [--index-name]` (columns `date,value[,change,pct_change]`); `doctor` checks calendar config and index-source status/freshness.
- [x] **`/market`**: leads with the NEPSE regime (`compute_regime`/`format_market_message`) with explicit **Unavailable** states (short/stale/empty data) + sector index list + existing data coverage.
- [x] **Scheduler**: post-close `index_fetch` job at close+grace; all cron strings now derive from `MarketClock`.
- [x] **Backtest benchmark** now uses the stored NEPSE index series over the same window (falls back to the single-stock approximation when no index data), labelled in `/report`.
- [x] Tests (`tests/test_index.py`, 24 tests): fixture parsing/validation/regime/escaping, Mon–Fri **and** Sun–Thu clock config, holiday-aware `last_expected_trading_day`, `TRADING_DAYS` validator, idempotent upsert, disabled/with-source/issue sync paths, CSV import, fake-client `fetch_latest`/`list_indices`, circuit-breaker opening, and mocked `/market` (regime, sector, unavailable, stale). Network is always faked.

### Test Results
- 104 passed, ruff clean

## Summary
All milestones (M1-M12) complete. NEPSE Sense is fully scaffolded, with:
- Config, DB, CLI, doctor
- Source adapters + CSV import + caching
- Validation, canonical prices, corporate actions, source health
- Indicators + support/resistance
- Fundamentals + signal engine (explainable)
- Telegram bot (all commands, whitelist, charts, demo mode)
- Scheduler + digest + dedupe + status
- Backtester (no lookahead, walk-forward, configurable costs) + /report
- News: RSS ingest (robots.txt-checked, dedupe), pre-market briefing, /news, opt-in urgent alerts
- Quick stock lookup: plain-text/fuzzy lookup, candlestick charts, per-symbol alerts
- Config-driven market clock + NEPSE/sector index adapter (disabled by default on ToS grounds)
- Documentation + production hardening
