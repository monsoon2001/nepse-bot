from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DAY_NAMES = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Telegram
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    allowed_telegram_ids: list[int] = Field(default_factory=list, alias="ALLOWED_TELEGRAM_IDS")

    # Database
    db_url: str = Field(default="sqlite:///./nepse_sense.db", alias="DB_URL")

    # Scheduler
    timezone: str = Field(default="Asia/Kathmandu", alias="TIMEZONE")

    # Trading calendar / market session.
    # trading_days: Python weekday numbers, Mon=0 .. Sun=6.
    # Default Mon-Fri because recent MeroLagani index dates include Fridays and
    # no Sundays. VERIFY against NEPSE before relying on this (NEPSE has
    # historically traded Sun-Thu) — set TRADING_DAYS=sun,mon,tue,wed,thu for that.
    trading_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], alias="TRADING_DAYS")
    session_open: str = Field(default="11:00", alias="SESSION_OPEN")
    session_close: str = Field(default="15:00", alias="SESSION_CLOSE")
    data_grace_minutes: int = Field(default=30, alias="DATA_GRACE_MINUTES")

    # Data Sources
    enable_experimental_live: bool = Field(default=False, alias="ENABLE_EXPERIMENTAL_LIVE")
    # MeroLagani index adapter. DISABLED by default: their Terms (§3) prohibit
    # automated data collection (scripts/scraping/robots) and robots.txt 404s.
    # See docs/DATA_SOURCES.md §8 before enabling.
    enable_merolagani: bool = Field(default=False, alias="ENABLE_MEROLAGANI")

    # Alerts
    alerts_post_close_time: str = Field(default="15:45", alias="ALERTS_POST_CLOSE_TIME")

    # News (RSS only — HTML scraping is never enabled by default).
    # Default = OnlineKhabar *business* category feed (robots.txt non-restrictive,
    # feed verified working; the main/general feed carries no market news —
    # see docs/DATA_SOURCES.md §7). Set NEWS_FEED_URLS="" to disable.
    news_feed_urls: list[str] = Field(
        default_factory=lambda: [
            "https://www.onlinekhabar.com/content/business/feed"
        ],
        alias="NEWS_FEED_URLS",
    )
    news_briefing_time: str = Field(default="10:00", alias="NEWS_BRIEFING_TIME")
    news_max_items: int = Field(default=10, alias="NEWS_MAX_ITEMS")

    # Network
    user_agent: str = Field(
        default="nepse-sense/0.1.0",
        alias="USER_AGENT",
    )
    request_timeout: int = Field(default=30, alias="REQUEST_TIMEOUT")
    request_retries: int = Field(default=3, alias="REQUEST_RETRIES")

    @property
    def project_root(self) -> Path:
        return Path(__file__).parent.parent

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @field_validator("allowed_telegram_ids", mode="before")
    @classmethod
    def _parse_allowed_ids(cls, v):
        if v is None:
            return []
        if isinstance(v, (int, float)):
            return [int(v)]
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @field_validator("news_feed_urls", mode="before")
    @classmethod
    def _parse_news_feeds(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            # comma-separated in .env; empty string = all news sources disabled
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @field_validator("trading_days", mode="before")
    @classmethod
    def _parse_trading_days(cls, v):
        """Accept a list of ints, or a comma string of ints/day-names.

        "sun,mon,tue,wed,thu" -> [6, 0, 1, 2, 3]; "0,1,2,3,4" -> [0,1,2,3,4].
        """
        if v is None:
            return [0, 1, 2, 3, 4]
        if isinstance(v, (list, tuple)):
            items = list(v)
        elif isinstance(v, int):
            return [int(v)]
        elif isinstance(v, str):
            items = [x.strip() for x in v.split(",") if x.strip()]
        else:
            return v
        out: list[int] = []
        for item in items:
            if isinstance(item, int):
                out.append(item)
                continue
            s = str(item).strip().lower()
            if s.isdigit():
                out.append(int(s))
            elif s in _DAY_NAMES:
                out.append(_DAY_NAMES[s])
            else:
                raise ValueError(f"Unknown trading day: {item!r}")
        return sorted(set(out))

    def model_post_init(self, __context) -> None:
        # Parse allowed telegram IDs from comma-separated string if needed
        if isinstance(self.allowed_telegram_ids, str):
            self.allowed_telegram_ids = [
                int(x.strip()) for x in self.allowed_telegram_ids.split(",") if x.strip()
            ]


settings = Settings()
