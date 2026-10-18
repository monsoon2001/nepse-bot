from datetime import date

from .base import BaseSchema


class EventModel(BaseSchema):
    symbol: str | None = None
    date: date
    event_type: str
    description: str | None = None
    adjustment_factor: float = 1.0
    source: str = "manual"
