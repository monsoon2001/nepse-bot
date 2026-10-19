from abc import ABC, abstractmethod
from datetime import date

from nepse_sense.schemas.event import EventModel
from nepse_sense.schemas.index import IndexRow
from nepse_sense.schemas.price import PriceOHLCV
from nepse_sense.schemas.symbol import SymbolModel


class PriceSource(ABC):
    @abstractmethod
    async def fetch_symbols(self) -> list[SymbolModel]:
        pass

    @abstractmethod
    async def fetch_history(self, symbol: str, start: date, end: date) -> list[PriceOHLCV]:
        pass

    @abstractmethod
    async def fetch_daily_snapshot(self, date: date) -> list[PriceOHLCV]:
        pass


class NoticeSource(ABC):
    @abstractmethod
    async def fetch_notices(self, since: date | None = None) -> list[EventModel]:
        pass


class BrokerDataSource(ABC):
    @abstractmethod
    async def fetch_broker_data(self, symbol: str | None = None) -> str:
        return "Unavailable"


class IndexSource(ABC):
    """Contract for index history providers (NEPSE / sector indices).

    Sync (not async) because the MeroLagani client is a careful sync httpx
    client (GET + POST paging, circuit breaker, throttle) and its consumers —
    the post-close scheduler job and the CLI backfill — are both sync. The
    /market command only reads the DB, it never fetches.
    """

    @abstractmethod
    def fetch_latest(self, index_name: str = "NEPSE") -> list[IndexRow]:
        """Latest slice of daily index rows (one cheap request)."""

    @abstractmethod
    def fetch_history(
        self, index_name: str = "NEPSE", max_pages: int = 30
    ) -> list[IndexRow]:
        """Older history, paging back as far as the source allows."""

    @abstractmethod
    def list_indices(self) -> dict[str, str]:
        """Map of index display name -> source option value."""
