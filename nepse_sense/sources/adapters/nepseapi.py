from datetime import date

from nepse_sense.config import settings
from nepse_sense.logging import logger
from nepse_sense.schemas.price import PriceOHLCV
from nepse_sense.schemas.symbol import SymbolModel
from nepse_sense.sources.base import PriceSource


class NepseAPIAdapter(PriceSource):
    """NEPSEAPI unofficial live-data experiment.

    OPTIONAL - Disabled by default (ENABLE_EXPERIMENTAL_LIVE=false).
    Any alert from it labelled EXPERIMENTAL / UNVERIFIED.
    """

    IS_VERIFIED = False
    STATUS = "EXPERIMENTAL/UNVERIFIED"
    ENABLED = settings.enable_experimental_live

    async def fetch_symbols(self) -> list[SymbolModel]:
        if not self.ENABLED:
            logger.debug("NepseAPIAdapter disabled (ENABLE_EXPERIMENTAL_LIVE=false)")
            return []
        logger.warning("NepseAPIAdapter.fetch_symbols() - EXPERIMENTAL/UNVERIFIED")
        return []

    async def fetch_history(self, symbol: str, start: date, end: date) -> list[PriceOHLCV]:
        if not self.ENABLED:
            return []
        logger.warning("NepseAPIAdapter.fetch_history() - EXPERIMENTAL/UNVERIFIED")
        return []

    async def fetch_daily_snapshot(self, _date: date) -> list[PriceOHLCV]:
        if not self.ENABLED:
            return []
        logger.warning("NepseAPIAdapter.fetch_daily_snapshot() - EXPERIMENTAL/UNVERIFIED")
        return []
