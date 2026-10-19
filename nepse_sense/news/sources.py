"""News source adapters. RSS only — HTML scraping is not implemented."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import httpx
from defusedxml import ElementTree

from nepse_sense.config import settings
from nepse_sense.logging import logger
from nepse_sense.news.robots import is_fetch_permitted


@dataclass
class FetchedItem:
    headline: str
    url: str
    source: str
    published_at: datetime  # aware, local tz


class NewsSource(ABC):
    name: str = "news"

    @abstractmethod
    async def fetch(
        self, since: datetime, until: datetime | None = None
    ) -> list[FetchedItem]:
        """Fetch items published in [since, until]. Raises on failure."""


def _parse_pubdate(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _text(el, *tags: str) -> str:
    for tag in tags:
        child = el.find(tag)
        if child is not None and child.text:
            return child.text.strip()
    return ""


class RssNewsSource(NewsSource):
    """RSS 2.0 feed reader. Only checks robots.txt; never scrapes HTML pages."""

    def __init__(self, feed_url: str, name: str | None = None,
                 robots_check=is_fetch_permitted):
        self.feed_url = feed_url
        self.name = name or urlparse_host(feed_url)
        self._robots_check = robots_check

    async def fetch(
        self, since: datetime, until: datetime | None = None
    ) -> list[FetchedItem]:
        if not self._robots_check(self.feed_url):
            raise PermissionError(f"robots.txt disallows fetching {self.feed_url}")
        async with httpx.AsyncClient(
            headers={"User-Agent": settings.user_agent},
            timeout=httpx.Timeout(settings.request_timeout),
            follow_redirects=True,
        ) as client:
            resp = await client.get(self.feed_url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "xml" not in content_type and "rss" not in content_type:
                # e.g. a soft-404 HTML page — not a feed
                raise ValueError(f"{self.feed_url} is not an RSS feed ({content_type})")
            body = resp.text
        return self._parse(body, since, until)

    def _parse(
        self, body: str, since: datetime, until: datetime | None
    ) -> list[FetchedItem]:
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError as e:
            raise ValueError(f"invalid XML from {self.feed_url}: {e}") from e

        items: list[FetchedItem] = []
        now_until = until or datetime.max.replace(tzinfo=UTC)
        for item in root.iter("item"):
            headline = _text(item, "title")
            if not headline:
                continue
            link = _text(item, "link")
            published = _parse_pubdate(_text(item, "pubDate", "date"))
            if published is None:
                continue
            local = published.astimezone(ZoneInfo(settings.timezone))
            ref_since = since if since.tzinfo else since.replace(tzinfo=UTC)
            ref_until = now_until if now_until.tzinfo else now_until.replace(tzinfo=UTC)
            if ref_since <= published <= ref_until:
                items.append(
                    FetchedItem(
                        headline=headline,
                        url=link,
                        source=self.name,
                        published_at=local,
                    )
                )
        return items


def urlparse_host(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).netloc.replace("www.", "")


def get_enabled_news_sources(
    feed_urls: list[str] | None = None, robots_check=is_fetch_permitted
) -> list[NewsSource]:
    """Sources allowed by config (NEWS_FEED_URLS) and robots.txt.

    Empty/absent config → no sources enabled (news is opt-in and RSS-only).
    """
    urls = settings.news_feed_urls if feed_urls is None else feed_urls
    sources: list[NewsSource] = []
    for url in urls:
        url = (url or "").strip()
        if not url:
            continue
        if not robots_check(url):
            logger.info(f"news source disabled by robots.txt: {url}")
            continue
        sources.append(RssNewsSource(url, robots_check=robots_check))
    return sources


def no_sources_enabled_reason(feed_urls: list[str] | None = None) -> str | None:
    """Human-readable reason when no source is enabled (for explicit messages)."""
    urls = settings.news_feed_urls if feed_urls is None else feed_urls
    if not any((u or "").strip() for u in urls):
        return (
            "No permitted news source is enabled "
            "(NEWS_FEED_URLS is empty; RSS-only, robots.txt checked)."
        )
    return None
