from datetime import datetime

from nepse_sense.db.engine import SessionLocal
from nepse_sense.db.models import SourceHealth


class SourceHealthTracker:
    def __init__(self):
        self.db = SessionLocal()

    def __del__(self):
        try:
            self.db.close()
        except Exception:
            from nepse_sense.logging import logger
            logger.debug("Error closing db")

    def record_success(self, source_name: str, response_time_ms: int = None, details: dict = None):
        health = (
            self.db.query(SourceHealth)
            .filter(SourceHealth.source_name == source_name)
            .order_by(SourceHealth.id.desc())
            .first()
        )
        if not health:
            health = SourceHealth(source_name=source_name)
        health.status = "ok"
        health.last_success = datetime.utcnow()
        health.last_check = datetime.utcnow()
        health.error_count = 0
        if response_time_ms is not None:
            health.response_time_ms = response_time_ms
        if details:
            health.details = details
        self.db.add(health)
        self.db.commit()

    def record_failure(self, source_name: str, error_msg: str = None, details: dict = None):
        health = (
            self.db.query(SourceHealth)
            .filter(SourceHealth.source_name == source_name)
            .order_by(SourceHealth.id.desc())
            .first()
        )
        if not health:
            health = SourceHealth(source_name=source_name)
        health.status = "error"
        health.last_check = datetime.utcnow()
        health.error_count = (health.error_count or 0) + 1
        details = details or {}
        if error_msg:
            details["error"] = error_msg
        health.details = details
        self.db.add(health)
        self.db.commit()

    def get_health_status(self, source_name: str = None):
        query = self.db.query(SourceHealth)
        if source_name:
            query = query.filter(SourceHealth.source_name == source_name)
        return query.order_by(SourceHealth.last_check.desc()).all()
