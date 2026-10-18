from datetime import date

from nepse_sense.logging import logger
from nepse_sense.schemas.event import EventModel
from nepse_sense.sources.base import NoticeSource


class SebonNoticeAdapter(NoticeSource):
    """SEBON notices adapter.

    Disabled by default unless programmatic access is clearly permitted.
    Status: UNVERIFIED, DISABLED by default
    """

    ENABLED = False
    IS_VERIFIED = False
    STATUS = "UNVERIFIED - DISABLED BY DEFAULT"

    async def fetch_notices(self, since: date | None = None) -> list[EventModel]:
        if not self.ENABLED:
            logger.debug("SebonNoticeAdapter disabled by default")
            return []
        logger.warning("SebonNoticeAdapter.fetch_notices() - UNVERIFIED")
        return []


class NepalstockNoticeAdapter(NoticeSource):
    """Nepalstock.com notices adapter.

    Disabled by default unless programmatic access is clearly permitted.
    Status: UNVERIFIED, DISABLED by default
    """

    ENABLED = False
    IS_VERIFIED = False
    STATUS = "UNVERIFIED - DISABLED BY DEFAULT"

    async def fetch_notices(self, since: date | None = None) -> list[EventModel]:
        if not self.ENABLED:
            logger.debug("NepalstockNoticeAdapter disabled by default")
            return []
        logger.warning("NepalstockNoticeAdapter.fetch_notices() - UNVERIFIED")
        return []
