from abc import ABC, abstractmethod
from datetime import date

from nepse_sense.schemas.event import EventModel
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
