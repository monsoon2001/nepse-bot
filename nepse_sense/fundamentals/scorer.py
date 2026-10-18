from dataclasses import dataclass, field


@dataclass
class FundamentalScoreResult:
    score: float | None = None
    breakdown: dict = field(default_factory=dict)
    unavailable_reason: str | None = None


class FundamentalScorer:
    """Transparent 0-100 quality score with visible breakdown."""

    def __init__(
        self,
        max_pe: float = 25.0,
        min_pb: float = 0.5,
        max_pb: float = 5.0,
        min_eps: float = 0.0,
    ):
        self.max_pe = max_pe
        self.min_pb = min_pb
        self.max_pb = max_pb
        self.min_eps = min_eps

    def score(
        self,
        eps: float | None = None,
        pe: float | None = None,
        book_value: float | None = None,
        pb: float | None = None,
        sector_pe: float | None = None,
        close: float | None = None,
    ) -> FundamentalScoreResult:
        if eps is None and pe is None and book_value is None and pb is None:
            return FundamentalScoreResult(
                score=None, unavailable_reason="No fundamental data available"
            )
        breakdown: dict[str, float] = {}
        total = 0.0
        max_total = 0.0
        if eps is not None and eps > self.min_eps:
            breakdown["eps"] = min(30.0, max(0.0, eps * 2))
            total += breakdown["eps"]
        max_total += 30.0
        if pe is not None and pe > 0:
            if pe <= self.max_pe:
                breakdown["pe"] = 25.0 * (1 - pe / self.max_pe) + 5
            else:
                breakdown["pe"] = max(0.0, 5.0 * (self.max_pe / pe))
            breakdown["pe"] = min(breakdown["pe"], 25.0)
            total += breakdown["pe"]
        max_total += 25.0
        if book_value is not None and close is not None and close > 0 and book_value > 0:
            if pb is None:
                pb = close / book_value
            if self.min_pb <= pb <= self.max_pb:
                breakdown["pb"] = 20.0
            elif pb < self.min_pb:
                breakdown["pb"] = 10.0
            else:
                breakdown["pb"] = max(0.0, 20.0 * (self.max_pb / pb))
            breakdown["pb"] = min(breakdown["pb"], 20.0)
            total += breakdown["pb"]
        max_total += 20.0
        if sector_pe is not None and pe is not None and sector_pe > 0:
            if pe <= sector_pe:
                breakdown["relative_pe"] = 15.0
            else:
                breakdown["relative_pe"] = max(0.0, 15.0 * (sector_pe / pe))
            breakdown["relative_pe"] = min(breakdown["relative_pe"], 15.0)
            total += breakdown["relative_pe"]
        max_total += 15.0
        if max_total == 0:
            return FundamentalScoreResult(
                score=None, unavailable_reason="Insufficient fundamental data for scoring"
            )
        normalized = (total / max_total) * 100
        breakdown["_total_raw"] = total
        breakdown["_max_total"] = max_total
        breakdown["_normalized"] = normalized
        return FundamentalScoreResult(score=round(normalized, 2), breakdown=breakdown)
