from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from nepse_sense.config import settings
from nepse_sense.logging import logger


class HttpClient:
    def __init__(self):
        self.headers = {
            "User-Agent": settings.user_agent,
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        self.timeout = httpx.Timeout(settings.request_timeout)
        self._client = httpx.AsyncClient(
            headers=self.headers,
            timeout=self.timeout,
            follow_redirects=True,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._client.aclose()

    @retry(
        stop=stop_after_attempt(settings.request_retries),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> httpx.Response:
        logger.debug(f"GET {url} params={params}")
        response = await self._client.get(url, params=params, **kwargs)
        response.raise_for_status()
        return response

    async def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        response = await self.get(url, params=params, **kwargs)
        return response.json()

    async def get_text(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        **kwargs,
    ) -> str:
        response = await self.get(url, params=params, **kwargs)
        return response.text
