from datetime import date

from nepse_sense.logging import logger
from nepse_sense.schemas.price import PriceOHLCV
from nepse_sense.schemas.symbol import SymbolModel
from nepse_sense.sources.base import PriceSource


class ShareSansarAdapter(PriceSource):
    """ShareSansar historical archive API adapter.

    Based on https://omitnomis.github.io/ - UNVERIFIED against live API.
    Marked as UNVERIFIED until live testing is performed.
    """

    BASE_URL = "https://api.sharesansar.com"
    IS_VERIFIED = False
    STATUS = "UNVERIFIED"

    async def fetch_symbols(self) -> list[SymbolModel]:
        logger.warning("ShareSansarAdapter.fetch_symbols() - UNVERIFIED against live API")
        return []

    async def fetch_history(self, symbol: str, start: date, end: date) -> list[PriceOHLCV]:
        logger.warning("ShareSansarAdapter.fetch_history() - UNVERIFIED against live API")
        return []

    async def fetch_daily_snapshot(self, _date: date) -> list[PriceOHLCV]:
        logger.warning("ShareSansarAdapter.fetch_daily_snapshot() - UNVERIFIED against live API")
        return []
