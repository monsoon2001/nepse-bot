# Data Sources

This document records findings about NEPSE data sources including endpoints, schemas, rate limits, licenses, and verification status.

## Status Legend
- **VERIFIED**: Endpoints/schemas confirmed against documentation or real responses
- **UNVERIFIED**: Built against known references but not fully verified against live API
- **DISABLED**: Not enabled by default due to access/permission concerns
- **EXPERIMENTAL**: For personal/educational use only, never sole basis for signals

## 1. ShareSansar historical archive API
- **URL**: https://api.sharesansar.com (per project references: https://omitnomis.github.io/)
- **Role**: PRIMARY - historical OHLCV, all-stock daily snapshots, symbol list, market recap
- **Status**: **UNVERIFIED** - Built against common API patterns from references; not tested against live API
- **Default**: Enabled (as primary source)
- **Notes**: Unofficial API. Requires proper rate limiting and custom User-Agent. Terms not fully verified - use respectfully.
- **Adapter**: `nepse_sense.sources.adapters.sharesansar.ShareSansarAdapter`

## 2. NEPSE Data daily archive (GitHub)
- **Role**: SECONDARY - cross-validation + bulk backfill
- **Status**: **UNVERIFIED** - Structure inferred from project references; license/redistribution terms to be verified
- **Default**: Enabled as secondary for validation
- **Notes**: Check actual repository license before bulk redistribution. Used for data quality cross-checking.
- **Adapter**: `nepse_sense.sources.adapters.nepse_data.NepseDataArchiveAdapter`

## 3. NEPSEAPI (unofficial live-data experiment)
- **Role**: OPTIONAL - experimental live data
- **Status**: **EXPERIMENTAL / UNVERIFIED**
- **Default**: **DISABLED** - `ENABLE_EXPERIMENTAL_LIVE=false` (configurable via env)
- **Critical Rule**: Any alert from this source must be labelled `EXPERIMENTAL / UNVERIFIED` and it must NEVER be the sole basis for an alert/signal
- **Adapter**: `nepse_sense.sources.adapters.nepseapi.NepseAPIAdapter`

## 4. Notices (sebon.gov.np, nepalstock.com)
- **Role**: NoticeSource for corporate actions, announcements
- **Status**: **UNVERIFIED, DISABLED BY DEFAULT**
- **Default**: Disabled unless programmatic access is clearly permitted
- **Notes**: Need to check robots.txt, ToS, and programmatic access permissions before enabling. Currently returns empty results.
- **Adapters**: `nepse_sense.sources.adapters.notices.SebonNoticeAdapter`, `NepalstockNoticeAdapter`

## 5. CSV Import
- **Role**: Fallback if all web sources break
- **Status**: **VERIFIED** (implemented and tested)
- **Default**: Always available
- **Usage**: `python -m nepse_sense import-csv --type prices file.csv`
- **Supported types**: OHLCV (prices), fundamentals, events

## 6. Manual events (data/events.csv)
- **Role**: Bonus/dividend/rights/book-closure manual entry
- **Status**: **VERIFIED** (implemented)
- **Default**: Always available
- **Format**: CSV with date, symbol, event_type, description, adjustment_factor

## Implementation Notes
- All adapters implement abstract interfaces (`PriceSource`, `NoticeSource`, `BrokerDataSource`)
- Custom User-Agent set via config (`USER_AGENT`)
- Retries with exponential backoff (tenacity) - configurable via `REQUEST_RETRIES`
- Timeouts configurable via `REQUEST_TIMEOUT`
- Raw response caching via `ResponseCache` (24h TTL by default)
- Rate limiting via `RateLimiter`
- Fixtures in `tests/fixtures/` for testing without network access
