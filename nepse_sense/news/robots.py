"""robots.txt permission checks for news fetches.

Policy: RSS is the only fetch method we ever use (no HTML scraping).
Before fetching a feed we check the site's robots.txt; if it explicitly
disallows our user-agent for the feed path, the source stays disabled.

Rules honoured:
- 404 / empty response  → no restrictions stated → permitted
- 200 with Disallow for our agent (or `*`) matching the path → denied
- 5xx / network error   → UNKNOWN → treated as NOT permitted (conservative)
"""

from __future__ import annotations

import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from nepse_sense.config import settings
from nepse_sense.logging import logger

_CACHE_TTL = 24 * 3600
_cache: dict[str, tuple[float, bool]] = {}


def _agent_token() -> str:
    # "nepse-sense/0.1.0 (...)" -> "nepse-sense"
    ua = settings.user_agent or "nepse-sense"
    return ua.split("/")[0].strip().lower()


def _parse_robots(body: str, url_path: str) -> bool:
    """True if fetching `url_path` is permitted for our user-agent."""
    parser = RobotFileParser()
    parser.parse(body.splitlines())
    agent = _agent_token()
    # can_fetch accepts the agent token; robots rules are case-insensitive
    if parser.can_fetch(agent, url_path):
        return True
    # fall back to the wildcard user-agent entry
    return parser.can_fetch("*", url_path)


def is_fetch_permitted(url: str, force: bool = False) -> bool:
    """Check robots.txt for `url`. Cached per host for 24h."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    cache_key = f"{parsed.scheme}://{parsed.netloc}"
    now = time.time()
    if not force and cache_key in _cache:
        ts, allowed = _cache[cache_key]
        if now - ts < _CACHE_TTL:
            return allowed

    robots_url = f"{cache_key}/robots.txt"
    allowed = False
    try:
        resp = httpx.get(
            robots_url,
            headers={"User-Agent": settings.user_agent},
            timeout=10.0,
            follow_redirects=True,
        )
        if resp.status_code == 404:
            allowed = True  # no robots.txt → nothing restricted
        elif resp.status_code == 200:
            allowed = _parse_robots(resp.text, parsed.path)
        elif resp.status_code >= 500:
            allowed = False  # unknown → conservative
        else:
            allowed = False
    except Exception as e:  # network failure → conservative
        logger.warning(f"robots.txt check failed for {cache_key}: {e}")
        allowed = False
    _cache[cache_key] = (now, allowed)
    if not allowed:
        logger.info(f"robots.txt does not permit fetch of {url} — source stays disabled")
    return allowed


def clear_cache() -> None:
    _cache.clear()
