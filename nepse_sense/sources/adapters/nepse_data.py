from datetime import date

from nepse_sense.logging import logger
from nepse_sense.schemas.price import PriceOHLCV
from nepse_sense.schemas.symbol import SymbolModel
from nepse_sense.sources.base import PriceSource


class NepseDataArchiveAdapter(PriceSource):
    """NEPSE Data archive adapter (GitHub based).

    SECONDARY source for cross-validation and bulk backfill.
    Status: UNVERIFIED
    """

    IS_VERIFIED = False
    STATUS = "UNVERIFIED"

    async def fetch_symbols(self) -> list[SymbolModel]:
        logger.warning("NepseDataArchiveAdapter.fetch_symbols() - UNVERIFIED against live API")
        return []

    async def fetch_history(self, symbol: str, start: date, end: date) -> list[PriceOHLCV]:
        logger.warning("NepseDataArchiveAdapter.fetch_history() - UNVERIFIED against live API")
        return []

    async def fetch_daily_snapshot(self, _date: date) -> list[PriceOHLCV]:
        logger.warning("NepseDataArchiveAdapter.fetch_daily_snapshot() - UNVERIFIED")
        return []
