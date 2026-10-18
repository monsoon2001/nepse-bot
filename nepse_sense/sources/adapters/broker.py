
from nepse_sense.logging import logger
from nepse_sense.sources.base import BrokerDataSource


class StubBrokerDataSource(BrokerDataSource):
    """Stub broker data source - always returns 'Unavailable'."""

    async def fetch_broker_data(self, symbol: str | None = None) -> str:  # type: ignore[override]
        logger.debug("Broker data is unavailable (stub)")
        return "Unavailable"
