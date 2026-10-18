from datetime import datetime

from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import DataQualityIssue, PriceCanonical, PriceDaily


class CanonicalBuilder:
    def __init__(self):
        self.db = SessionLocal()

    def __del__(self):
        try:
            self.db.close()
        except Exception:
            from nepse_sense.logging import logger

            logger.debug("Error closing db")

    def build_canonical_for_symbol_date(self, symbol: str, dt) -> PriceCanonical | None:
        prices = (
            self.db.query(PriceDaily)
            .filter(PriceDaily.symbol == symbol, PriceDaily.date == dt)
            .all()
        )
        if not prices:
            return None
        # Check for critical issues
        critical_issues = (
            self.db.query(DataQualityIssue)
            .filter(
                DataQualityIssue.symbol == symbol,
                DataQualityIssue.date == dt,
                DataQualityIssue.severity == "critical",
                DataQualityIssue.resolved.is_(False),
            )
            .all()
        )
        if critical_issues:
            return None  # Don't build canonical if critical issues exist
        # Use primary/first source as base; merge others
        base = prices[0]
        sources = list({p.source for p in prices})
        canonical = PriceCanonical(
            symbol=symbol,
            date=dt,
            open=base.open,
            high=base.high,
            low=base.low,
            close=base.close,
            volume=base.volume,
            turnover=base.turnover,
            sources=sources,
            provenance={
                "primary_source": base.source,
                "all_sources": sources,
                "count": len(prices),
                "built_at": datetime.utcnow().isoformat(),
            },
            is_validated=True,
        )
        self.db.add(canonical)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
        return canonical

    def build_all_canonical(self, start=None, end=None):
        query = self.db.query(PriceDaily.symbol, PriceDaily.date).distinct()
        if start:
            query = query.filter(PriceDaily.date >= start)
        if end:
            query = query.filter(PriceDaily.date <= end)
        results = query.all()
        count = 0
        for symbol, dt in results:
            if self.build_canonical_for_symbol_date(symbol, dt):
                count += 1
        return count
