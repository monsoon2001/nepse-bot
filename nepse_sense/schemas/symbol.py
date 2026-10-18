from .base import BaseSchema


class SymbolModel(BaseSchema):
    symbol: str
    company_name: str | None = None
    sector: str | None = None
    is_active: bool = True
