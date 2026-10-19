from nepse_sense.config import settings
from nepse_sense.sources.adapters.broker import StubBrokerDataSource
from nepse_sense.sources.adapters.merolagani_index import MeroLaganiIndexSource
from nepse_sense.sources.adapters.nepse_data import NepseDataArchiveAdapter
from nepse_sense.sources.adapters.nepseapi import NepseAPIAdapter
from nepse_sense.sources.adapters.notices import (
    NepalstockNoticeAdapter,
    SebonNoticeAdapter,
)
from nepse_sense.sources.adapters.sharesansar import ShareSansarAdapter


class SourceFactory:
    @staticmethod
    def get_price_sources():
        return [
            ShareSansarAdapter(),
            NepseDataArchiveAdapter(),
            NepseAPIAdapter(),
        ]

    @staticmethod
    def get_primary_price_source():
        return ShareSansarAdapter()

    @staticmethod
    def get_secondary_price_source():
        return NepseDataArchiveAdapter()

    @staticmethod
    def get_notice_sources():
        return [
            SebonNoticeAdapter(),
            NepalstockNoticeAdapter(),
        ]

    @staticmethod
    def get_broker_source():
        return StubBrokerDataSource()

    @staticmethod
    def get_index_source():
        """Index source, or None when disabled (ENABLE_MEROLAGANI=false).

        Kept disabled by default because automated access is prohibited by the
        site's Terms (docs/DATA_SOURCES.md §8).
        """
        if not settings.enable_merolagani:
            return None
        return MeroLaganiIndexSource()
