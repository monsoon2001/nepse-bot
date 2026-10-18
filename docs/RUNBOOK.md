# Runbook

Operational guide for running NEPSE Sense.

## Setup and Installation
- See README.md for initial setup

## Running with tmux
```bash
tmux new -s nepse-sense
source .venv/bin/activate
python -m nepse_sense run-bot
# Ctrl+B, D to detach
```

## Running with launchd (macOS)

Create `~/Library/LaunchAgents/com.nepse.sense.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.nepse.sense</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>-m</string>
    <string>nepse_sense</string>
    <string>run-bot</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/YOU/Downloads/nepse-bot</string>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/nepse-sense.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/nepse-sense.err</string>
</dict>
</plist>
```

Then:
```bash
launchctl load ~/Library/LaunchAgents/com.nepse.sense.plist
launchctl start com.nepse.sense
```

## Backup and Restore

The database is a single SQLite file (`nepse_sense.db` by default).

### Backup
```bash
# Stop the bot first, then:
cp nepse_sense.db nepse_sense.db.backup.$(date +%Y%m%d)
# Or use sqlite3 for a consistent online backup:
sqlite3 nepse_sense.db ".backup nepse_sense.db.backup.$(date +%Y%m%d)"
```

### Restore
```bash
# Stop the bot
rm -f nepse_sense.db nepse_sense.db-shm nepse_sense.db-wal
cp nepse_sense.db.backup.YYYYMMDD nepse_sense.db
python -m nepse_sense init-db   # safe; creates tables if missing
```

### Rebuild from scratch
```bash
rm -f nepse_sense.db nepse_sense.db-shm nepse_sense.db-wal
python -m nepse_sense init-db
python -m nepse_sense import-csv <prices.csv> --import-type prices
python -m nepse_sense import-csv <fundamentals.csv> --import-type fundamentals
python -m nepse_sense scan
```

## Alerts and Notifications

- Post-close digest is scheduled at 15:45 NPT (Sun–Thu) via APScheduler.
- Alerts are deduplicated per-user via the `alerts_sent` table (1-day window by default).
- Per-user `alerts_enabled` flag lives in `users.settings` JSON.
- Single "No signals today" message is sent when data is stale or unavailable.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `doctor` shows `Database connection FAIL` | DB file missing or bad `DB_URL` | `python -m nepse_sense init-db`; check `.env` |
| `TELEGRAM_BOT_TOKEN not set` | Missing `.env` entry | Copy `.env.example` -> `.env`, fill token |
| Bot exits immediately | No allowed user IDs | Set `TELEGRAM_ALLOWED_USER_IDS` in `.env` |
| `scan` yields 0 signals | Insufficient history or all excluded | Import more data; check `/status` for exclusions |
| Signals stale / not updating | Latest data too old | Run `import-csv` or `ingest`; check `SourceHealth` |
| Schema errors after update | DB schema changed | Delete `nepse_sense.db*` and re-run `init-db` + re-import |
| Duplicate alerts | Dedupe window missed | Check `alerts_sent` table; adjust `dedupe_days` |
| `doctor` shows source FAIL | Live adapter unverified/offline | Expected in default stub mode; not a system failure |

## Health Checks

Run regularly:
```bash
python -m nepse_sense doctor   # environment, DB, token checks
```

In the bot:
```
/status   # source health, last scan, symbols scanned vs excluded, open issues
```

## Logs

- Application logs via `loguru` to stderr.
- `ScanRun` rows record every scan/ingest/health-ping with counts and status.
- launchd example writes to `/tmp/nepse-sense.log` and `/tmp/nepse-sense.err`.
