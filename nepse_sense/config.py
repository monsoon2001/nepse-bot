from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Telegram
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    allowed_telegram_ids: list[int] = Field(default_factory=list, alias="ALLOWED_TELEGRAM_IDS")

    # Database
    db_url: str = Field(default="sqlite:///./nepse_sense.db", alias="DB_URL")

    # Scheduler
    timezone: str = Field(default="Asia/Kathmandu", alias="TIMEZONE")

    # Data Sources
    enable_experimental_live: bool = Field(default=False, alias="ENABLE_EXPERIMENTAL_LIVE")

    # Alerts
    alerts_post_close_time: str = Field(default="15:45", alias="ALERTS_POST_CLOSE_TIME")

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

    def model_post_init(self, __context) -> None:
        # Parse allowed telegram IDs from comma-separated string if needed
        if isinstance(self.allowed_telegram_ids, str):
            self.allowed_telegram_ids = [
                int(x.strip()) for x in self.allowed_telegram_ids.split(",") if x.strip()
            ]


settings = Settings()
