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

## 7. News sources (RSS only)

Policy: **RSS is the only fetch method.** HTML scraping is not implemented and
never enabled by default. Before any feed is used, robots.txt is checked at
runtime (`nepse_sense/news/robots.py`): 404 → permitted, explicit Disallow →
the source stays disabled, 5xx/network error → treated as not permitted
(conservative). Items store headline + source + published time + link only —
no article text is fetched or stored.

Verified 2026-10-18 (robots.txt + feed probed directly):

| Source | robots.txt | RSS feed | Verdict |
|---|---|---|---|
| onlinekhabar.com | `User-agent: *`, nothing disallowed | business feed `https://www.onlinekhabar.com/content/business/feed` → 200, `application/rss+xml` (verified); main feed `/rss`→`/feed` works but carries **no market news** | **ENABLED BY DEFAULT** (business category feed) |
| sharesansar.com | `User-agent: *`, `Disallow:` (empty) | no RSS found (`/feed`, `/rss` return HTML) | not enabled |
| sebon.gov.np | `User-agent: *`, `Disallow:` (empty) | none (notices only) | not enabled (see §4) |
| merolagani.com | no robots.txt served (404) | `/feed`, `/Rss.aspx` return soft-404 HTML, not RSS | **disabled** — scraping would be required |
| ekantipur.com | content-signals preamble only, no Disallow | `/rss`, `/feed` → 404 | **disabled** — no RSS available |
| setopati.com | unreachable | unreachable | **disabled** |
| nepalstock.com | SPA HTML, not a real robots.txt | none known | **disabled** |

Configuration:
- `NEWS_FEED_URLS` — comma-separated RSS URLs. Default: OnlineKhabar business
  category feed (the main/general feed was tested: 55 items/week, **0** market-relevant
  headlines — it only carries general news, so it is not used).
  Set to empty (`NEWS_FEED_URLS=`) to disable news entirely; the 10:00
  briefing then explicitly reports *"No permitted news source is enabled"*.
- To add another feed: verify its robots.txt allows our user-agent, confirm a
  real RSS endpoint (Content-Type must be XML/RSS — soft-404 HTML is rejected),
  then append the URL to `NEWS_FEED_URLS`.

Impact scoring (`nepse_sense/news/impact.py`): deterministic keyword rules
covering Nepali + English market terms and both spellings (शेयर/सेयर बजार,
राष्ट्र बैंक, पुँजीबजार, बैंक/बैंकिङ, बीमा, लगानी, ऋण, लाभांश, बोनस,
नाफाविभाजन, मौद्रिक नीति, सर्किट, IPO/FPO, SEBON/सेबोन, NEPSE/नेपसे, etc.);
symbol mention +20, watchlist match +40, same-day corporate event +15,
source weight +5; capped at 100; high impact ≥ 60. Headlines with score 0
(no market relevance) are dropped at ingest — verified against the live
business feed: 12/55 relevant (NRB, bank M&A, share-market moves, bonus shares,
capital-market policy), general items correctly excluded.

## 8. NEPSE / sector index history (MeroLagani Indices.aspx)

Source: `https://merolagani.com/Indices.aspx` — daily NEPSE index and sector
index values (index value, absolute change, % change), paginated.

**Automated access is prohibited by the site's Terms of Service.** On
2026-10-18 the following was read directly from the site:

- `https://merolagani.com/Disclaimer.aspx` §3 (verbatim): the Terms disallow
  the use of *"scripts, APIs, screen scraping, data mining, robots, or other
  data gathering and extraction tools, regardless of their intended purposes"*.
- `https://merolagani.com/robots.txt` → **404** (no robots.txt is served).

Because §3 explicitly forbids automated collection *regardless of purpose*,
`robots.txt` being absent does **not** grant permission. The adapter therefore
ships **disabled by default**.

Policy:
- `ENABLE_MEROLAGANI=false` (default). While false, the fetch code path is never
  executed: the post-close scheduler job and `nepse_sense index-sync` return a
  `disabled` status and make **no network request**.
- **Do not** flip this to `true` and run it against the live site without
  confirming that automated access is acceptable for your use. The reference
  adapter is kept only so the parsing/validation/regime logic is reusable.
- The ToS-safe path is a **manual CSV import**:
  `nepse_sense import-index-csv <file.csv> [--index-name NEPSE]`
  (columns: `date,value` with optional `change,pct_change`; date is
  `YYYY-MM-DD` or `YYYY/MM/DD`).
- Paging back through history (ASP.NET postback) is **UNVERIFIED against the
  live site**. Parsing, validation, regime and message formatting are covered
  by fixture-based tests (`tests/test_index.py`).

Storage: `index_daily` table (unique on `index_name, day, source`), idempotent
upserts via `nepse_sense/indexing/service.py`. Critical validation issues
(`validate_rows`) are recorded in `data_quality_issues`.

Trading days come from `MarketClock` (`TRADING_DAYS`), **not** from this
adapter — see §Implementation Notes and `docs/ASSUMPTIONS.md`.

## Implementation Notes
- All adapters implement abstract interfaces (`PriceSource`, `NoticeSource`, `BrokerDataSource`, `IndexSource`)
- Custom User-Agent set via config (`USER_AGENT`)
- Retries with exponential backoff (tenacity) - configurable via `REQUEST_RETRIES`
- Timeouts configurable via `REQUEST_TIMEOUT`
- Raw response caching via `ResponseCache` (24h TTL by default)
- Rate limiting via `RateLimiter`
- Fixtures in `tests/fixtures/` for testing without network access
