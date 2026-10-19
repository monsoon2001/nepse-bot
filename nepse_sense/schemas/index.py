"""Index data schemas (NEPSE / sector indices).

Frozen dataclasses moved verbatim from the provided MeroLagani adapter so that
`sources.base.IndexSource` can reference `IndexRow` without inverting the
dependency (base must not import from adapters).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

SOURCE_NAME = "merolagani"


@dataclass(frozen=True)
class IndexRow:
    index_name: str
    day: date
    value: float
    change: float
    pct_change: float
    source: str = SOURCE_NAME


@dataclass(frozen=True)
class Issue:
    day: date
    severity: str  # "critical" | "warning"
    code: str
    detail: str


@dataclass
class MarketRegime:
    label: str  # Bullish | Mixed | Bearish | Unavailable
    as_of: date | None
    last_value: float | None
    day_change_pct: float | None
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stale: bool = False
    source: str = SOURCE_NAME
