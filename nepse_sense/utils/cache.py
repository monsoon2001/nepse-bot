import hashlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from nepse_sense.config import settings
from nepse_sense.logging import logger


class ResponseCache:
    def __init__(self, cache_dir: Path | None = None, ttl_hours: int = 24):
        self.cache_dir = cache_dir or settings.cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(hours=ttl_hours)

    def _get_cache_key(self, url: str, params: dict | None = None) -> str:
        key_data = {"url": url, "params": params or {}}
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get(self, url: str, params: dict | None = None) -> dict[str, Any] | None:
        cache_file = self.cache_dir / f"{self._get_cache_key(url, params)}.json"
        if not cache_file.exists():
            return None
        try:
            import time

            if time.time() - cache_file.stat().st_mtime > self.ttl.total_seconds():
                cache_file.unlink(missing_ok=True)
                return None
            with open(cache_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.debug(f"Cache get failed: {e}")
            return None

    def set(self, url: str, params: dict | None = None, data: dict[str, Any] | None = None):
        if data is None:
            return
        cache_file = self.cache_dir / f"{self._get_cache_key(url, params)}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.debug(f"Cache set failed: {e}")
