# Assumptions

Document any assumptions made during development here.

## Current Assumptions
- **Trading days default to Mon–Fri** (`TRADING_DAYS=0,1,2,3,4`), replacing the
  previous hardcoded Sunday–Thursday calendar. This is inferred from observed
  MeroLagani index data (recent dates include Fridays and no Sundays) and is
  **UNVERIFIED against NEPSE**. NEPSE has historically traded Sun–Thu; set
  `TRADING_DAYS=sun,mon,tue,wed,thu` (or `6,0,1,2,3`) to switch back. All
  scheduling, staleness, briefing and look-back logic reads this value via
  `MarketClock` — nothing hardcodes a weekday. `/status` and `nepse_sense
  doctor` warn if stored price data disagrees with `TRADING_DAYS`.
- **Market session** defaults to 11:00–15:00 NPT (`SESSION_OPEN`,
  `SESSION_CLOSE`) with a 30-minute post-close data grace
  (`DATA_GRACE_MINUTES`) before the current day's data is expected.
- **MeroLagani index adapter is disabled** (`ENABLE_MEROLAGANI=false`): the
  site's Terms of Service prohibit automated collection (see
  `docs/DATA_SOURCES.md` §8). Paging backfill is UNVERIFIED against the live
  site; use `import-index-csv` for a ToS-safe manual path.


