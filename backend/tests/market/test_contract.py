"""Contract tests: both MarketDataSource implementations must behave the same way."""

import asyncio

import pytest

from app.market.cache import PriceCache
from app.market.interface import MarketDataSource
from app.market.massive_client import MassiveDataSource
from app.market.simulator import SimulatorDataSource

from .fakes import FakeMassiveClient, snapshot

TICKERS = ("AAPL", "MSFT", "TSLA", "PYPL")


def _make(kind: str, cache: PriceCache) -> MarketDataSource:
    if kind == "simulator":
        return SimulatorDataSource(price_cache=cache, update_interval=60.0)
    client = FakeMassiveClient(snapshots=[snapshot(t, last=100.0) for t in TICKERS])
    return MassiveDataSource(api_key="k", price_cache=cache, poll_interval=60.0, client=client)


@pytest.fixture(params=["simulator", "massive"])
def kind(request) -> str:
    return request.param


@pytest.mark.asyncio
class TestMarketDataSourceContract:
    async def test_is_a_market_data_source(self, kind):
        assert isinstance(_make(kind, PriceCache()), MarketDataSource)

    async def test_start_populates_cache_with_normalized_tickers(self, kind):
        cache = PriceCache()
        source = _make(kind, cache)
        await source.start(["aapl", " MSFT ", "AAPL"])
        try:
            assert sorted(source.get_tickers()) == ["AAPL", "MSFT"]
            assert cache.get_price("AAPL") is not None
            assert cache.get_price("MSFT") is not None
            assert cache.get("AAPL").session_open == cache.get_price("AAPL")
        finally:
            await source.stop()

    async def test_add_ticker_idempotent_and_normalized(self, kind):
        cache = PriceCache()
        source = _make(kind, cache)
        await source.start(["AAPL"])
        try:
            await source.add_ticker("tsla")
            await source.add_ticker("TSLA ")
            assert source.get_tickers().count("TSLA") == 1
            assert "tsla" not in source.get_tickers()
        finally:
            await source.stop()

    async def test_remove_ticker_clears_cache_and_is_idempotent(self, kind):
        cache = PriceCache()
        source = _make(kind, cache)
        await source.start(["AAPL", "MSFT"])
        try:
            await source.remove_ticker("msft")
            await source.remove_ticker("MSFT")
            await source.remove_ticker("NEVER")
            assert source.get_tickers() == ["AAPL"]
            assert "MSFT" not in cache
        finally:
            await source.stop()

    async def test_stop_twice_and_no_writes_after_stop(self, kind):
        cache = PriceCache()
        source = _make(kind, cache)
        await source.start(["AAPL"])
        await source.stop()
        await source.stop()
        version = cache.version
        await asyncio.sleep(0.02)
        assert cache.version == version

    async def test_empty_start(self, kind):
        cache = PriceCache()
        source = _make(kind, cache)
        await source.start([])
        try:
            assert source.get_tickers() == []
            assert len(cache) == 0
        finally:
            await source.stop()
