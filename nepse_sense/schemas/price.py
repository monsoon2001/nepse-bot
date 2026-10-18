from datetime import date

from .base import BaseSchema


class PriceOHLCV(BaseSchema):
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float | None = None


class PriceDailyModel(BaseSchema):
    symbol: str
    date: date
    source: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    turnover: float | None = None
    raw_data: dict | None = None
