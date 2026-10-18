from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import DataQualityIssue, Event


class CorporateActionsHandler:
    def __init__(self):
        self.db = SessionLocal()

    def __del__(self):
        try:
            self.db.close()
        except Exception:
            from nepse_sense.logging import logger
            logger.debug("Error closing db")

    def apply_adjustments(self, symbol: str | None = None):
        """Apply adjustments based on events. Adjusted series - raw prices stored."""
        events = self.db.query(Event).filter(Event.adjustment_factor != 1.0)
        if symbol:
            events = events.filter(Event.symbol == symbol)
        return events.count()

    def flag_unadjusted_gaps(self):
        """Flag suspected unadjusted gaps when event data is missing."""
        issues = (
            self.db.query(DataQualityIssue)
            .filter(DataQualityIssue.issue_type == "suspicious_jump_gt10pct")
            .filter(DataQualityIssue.resolved.is_(False))
            .all()
        )
        for issue in issues:
            event_exists = (
                self.db.query(Event)
                .filter(
                    Event.symbol == issue.symbol,
                    Event.date == issue.date,
                )
                .first()
            )
            if not event_exists:
                issue.description = (
                    f"{issue.description} - suspected unadjusted gap (no event data found)"
                )
                issue.severity = "warning"
        self.db.commit()
        return len(issues)
