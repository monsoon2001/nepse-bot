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

`/start` `/help` `/top` `/stock SYMBOL` `/market` `/status` `/report` `/chart SYMBOL`
`/watchlist` `/add SYMBOL` `/remove SYMBOL` `/portfolio` `/brokers` `/addevent`

### Demo Mode

`run-bot --demo` seeds synthetic data (SYN01–SYN03) so you can try the bot without real data or a configured token. Demo mode uses `random` for generation only (not for signal logic).

## Configuration

- `.env` — secrets (bot token, allowed user IDs, DB URL). Copy from `.env.example`.
- `config/signals.yaml` — signal weights, category thresholds, confidence tiers.
- `config/holidays.csv` — NEPSE holiday calendar.
- Environment variables control source toggles, tolerances, circuit limits, and more (see `.env.example` and `nepse_sense/config.py`).

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
