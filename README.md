# NEPSE Sense

NEPSE Sense is an explainable stock scanner and Telegram bot for the Nepal Stock Exchange (NEPSE). It ingests market data, computes technical indicators, scores stocks, and surfaces transparent, rule-based signals through Telegram — with an emphasis on explainability and data-quality gating.

## Features

- **Explainable signals** — every signal includes a score, human-readable reasons, risk flags, and key levels (support/resistance, ATR, invalidation).
- **Data-quality gating** — symbols with unresolved critical issues, insufficient history, or stale data are excluded from signals.
- **Configurable signal engine** — weights and thresholds live in `config/signals.yaml` and are easy to tune.
- **Telegram bot** — interactive commands for top stocks, stock detail, charts, watchlists, portfolios, and events.
- **Backtester** — event-driven, next-day-open entry (no lookahead), configurable NEPSE costs, walk-forward split.
- **Daily digest + dedupe** — post-close digest with per-user settings and alert deduplication.
- **Source adapters** — pluggable adapters with caching, retries, and rate limiting. Live adapters are marked UNVERIFIED; stubs are used by default.

## Setup

### macOS Setup (<10 minutes)
```bash
# Clone or navigate to repo
cd nepse-bot

# Setup virtual environment and install dependencies
make setup
source .venv/bin/activate
pip install -r requirements.txt

# Initialize database
python -m nepse_sense init-db

# Run doctor to check setup
python -m nepse_sense doctor
```

## Telegram Setup

1. Create a bot with [@BotFather](https://t.me/BotFather)
2. Get your bot token
3. Find your Telegram ID (use [@userinfobot](https://t.me/userinfobot) or similar)
4. Copy `.env.example` to `.env` and fill in the values

## Usage

```bash
# Initialize database
python -m nepse_sense init-db

# Import data from CSV
python -m nepse_sense import-csv tests/fixtures/sample_prices.csv --import-type prices
python -m nepse_sense import-csv tests/fixtures/sample_fundamentals.csv --import-type fundamentals

# Import NEPSE / sector index history from CSV (ToS-safe manual path)
python -m nepse_sense import-index-csv index.csv --index-name NEPSE

# Fetch the latest index slice (disabled unless ENABLE_MEROLAGANI=true)
python -m nepse_sense index-sync

# Run scan (canonicalize -> indicators -> signals)
python -m nepse_sense scan

# Run backtest on stored signals
python -m nepse_sense backtest --min-score 50 --walk-forward

# Run bot (demo mode with synthetic data)
python -m nepse_sense run-bot --demo

# Run diagnostics
python -m nepse_sense doctor

# Full CLI help
python -m nepse_sense --help
```

### Bot Commands

`/start` `/help` `/top` `/stock SYMBOL` `/news [N|SYMBOL]` `/market` `/status` `/report` `/chart SYMBOL`
`/watchlist` `/add SYMBOL` `/remove SYMBOL` `/portfolio` `/brokers` `/addevent` `/profile`

### News & Briefings

- **Pre-market briefing** (10:00 NPT, on configured trading days, market holidays
  skipped): today's events and deadlines plus news since the last successful briefing —
  impact-ranked, watchlist stocks first, max 10 items (headline, source, published time,
  link only; no article text).
- **`/news`** — news since last market close; `/news 3` — last 3 days (max 7);
  `/news SYMBOL` — one stock. Paginated.
- **Urgent watchlist alerts** — opt-in (default OFF, toggle in `/profile`): during market
  hours, high-impact news about your watchlist stocks is pushed immediately.
- **Sources**: RSS only, robots.txt-checked at runtime. Default feed: OnlineKhabar
  (see `docs/DATA_SOURCES.md` §7). Set `NEWS_FEED_URLS=` (empty) to disable; the briefing
  then says explicitly that no permitted source is enabled.

### Demo Mode

`run-bot --demo` seeds synthetic data (SYN01–SYN03) so you can try the bot without real data or a configured token. Demo mode uses `random` for generation only (not for signal logic).

## Configuration

- `.env` — secrets (bot token, allowed user IDs, DB URL). Copy from `.env.example`.
- `config/signals.yaml` — signal weights, category thresholds, confidence tiers.
- `config/holidays.csv` — NEPSE holiday calendar.
- Environment variables control source toggles, tolerances, circuit limits, and more (see `.env.example` and `nepse_sense/config.py`).

### Trading calendar & market session

All scheduling, staleness, briefing and look-back logic is driven by `MarketClock`
(`nepse_sense/clock.py`) and config — nothing hardcodes a weekday:

- `TRADING_DAYS` — Python weekday numbers Mon=0..Sun=6 or names (`0,1,2,3,4` or
  `sun,mon,tue,wed,thu`). **Default Mon–Fri** (inferred from observed index dates;
  UNVERIFIED against NEPSE — see `docs/ASSUMPTIONS.md`).
- `SESSION_OPEN` / `SESSION_CLOSE` — market hours (default 11:00 / 15:00 NPT).
- `DATA_GRACE_MINUTES` — post-close grace before today's data is expected (default 30).

`/status` and `doctor` warn when stored prices disagree with `TRADING_DAYS`.

### Index data (MeroLagani)

`ENABLE_MEROLAGANI=false` by default — the site's Terms of Service prohibit automated
collection (see `docs/DATA_SOURCES.md` §8). Use `import-index-csv` for a ToS-safe manual
path; `index-sync` only fetches when explicitly enabled.

## Data Sources

See `docs/DATA_SOURCES.md` for adapter status. Live adapters (ShareSansar, NEPSE Data archive, NEPSEAPI) are marked **UNVERIFIED against live API**; the default path is stub/CSV-driven so the system is safe to run offline.

## Development

```bash
make test    # run pytest
make lint    # run ruff check
make format  # run ruff format
```

## Keeping it Alive

- Use `tmux` or `screen` to keep it running
- For macOS, use `launchd` (see RUNBOOK.md for details)

## Disclaimer

This is an educational tool. It is **not financial advice**. NEPSE cost rates and regulatory details used in the backtester are configurable defaults and must be verified against current NEPSE/SEBON published rates before real use. All live data adapters are UNVERIFIED and disabled by default.
