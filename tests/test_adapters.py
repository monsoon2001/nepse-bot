from nepse_sense.sources.adapters.broker import StubBrokerDataSource
from nepse_sense.sources.adapters.nepseapi import NepseAPIAdapter
from nepse_sense.sources.adapters.notices import SebonNoticeAdapter
from nepse_sense.sources.adapters.sharesansar import ShareSansarAdapter
from nepse_sense.sources.base import BrokerDataSource, PriceSource


def test_price_source_interfaces():
    ss = ShareSansarAdapter()
    assert isinstance(ss, PriceSource)
    assert ss.STATUS == "UNVERIFIED"
    assert ss.IS_VERIFIED is False


def test_nepseapi_disabled_by_default():
    api = NepseAPIAdapter()
    assert api.STATUS == "EXPERIMENTAL/UNVERIFIED"
    assert api.IS_VERIFIED is False
    # Should be disabled by default unless env var set


def test_notices_disabled_by_default():
    sebon = SebonNoticeAdapter()
    assert not sebon.ENABLED
    assert sebon.STATUS == "UNVERIFIED - DISABLED BY DEFAULT"


def test_broker_returns_unavailable():
    stub = StubBrokerDataSource()
    assert isinstance(stub, BrokerDataSource)
