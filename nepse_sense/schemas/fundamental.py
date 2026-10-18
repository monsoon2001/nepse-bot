from datetime import date

from .base import BaseSchema


class FundamentalModel(BaseSchema):
    symbol: str
    date: date
    eps: float | None = None
    pe: float | None = None
    book_value: float | None = None
    pb: float | None = None
    sector_pe: float | None = None
    sector_pb: float | None = None
    score: float | None = None
    score_breakdown: dict | None = None
    raw_data: dict | None = None
