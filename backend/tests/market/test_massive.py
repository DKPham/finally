"""Tests for MassiveDataSource, using real SDK models and a fake client (no network)."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import pytest
from massive.exceptions import BadResponse

from app.market.cache import PriceCache
from app.market.massive_client import (
    EOD_MODE,
    SNAPSHOT_MODE,
    MassiveDataSource,
    Quote,
    quote_from_snapshot,
)

from .fakes import MS_TS, NS_TS, FakeMassiveClient, grouped_bar, snapshot

NOT_AUTHORIZED = BadResponse(
    '{"status":"NOT_AUTHORIZED","request_id":"x",'
    '"message":"You are not entitled to this data. Please upgrade your plan."}'
)
BAD_KEY = BadResponse('{"status":"ERROR","request_id":"x","error":"Unknown API Key"}')


def _yesterday(days_back: int = 1) -> str:
    return (datetime.now(UTC).date() - timedelta(days=days_back)).isoformat()


def _source(cache: PriceCache, client: FakeMassiveClient, **kwargs) -> MassiveDataSource:
    kwargs.setdefault("poll_interval", 60.0)
    return MassiveDataSource(api_key="test-key", price_cache=cache, client=client, **kwargs)


class TestQuoteFromSnapshot:
    """Parsing of real TickerSnapshot objects."""

    def test_last_trade_price_and_sip_timestamp_in_ns(self):
        q = quote_from_snapshot(snapshot("AAPL", last=190.52, ns=1_731_753_600_000_000_000))
        assert q == Quote("AAPL", 190.52, 1_731_753_600.0)

    def test_timestamp_is_seconds_not_ms_or_ns(self):
        q = quote_from_snapshot(snapshot("AAPL", last=190.52, ns=NS_TS))
        assert q.timestamp == pytest.approx(NS_TS / 1e9)
        assert 1e9 < q.timestamp < 1e10  # plausible Unix seconds

    @pytest.mark.parametrize(
        "kwargs,expected",
        [
            ({"minute": 190.4, "day": 0, "prev": 189.0}, 190.4),  # no last trade
            ({"day": 190.1, "prev": 189.0}, 190.1),  # no last trade, no minute bar
            ({"day": 0, "prev": 189.0}, 189.0),  # right after the daily reset
            ({"last": 0, "minute": 0, "day": 0, "prev": 188.5}, 188.5),  # zeros skipped
        ],
    )
    def test_price_fallback_chain(self, kwargs, expected):
        assert quote_from_snapshot(snapshot("AAPL", **kwargs)).price == expected

    def test_falls_back_to_updated_timestamp(self):
        q = quote_from_snapshot(snapshot("AAPL", prev=189.0, updated=NS_TS))
        assert q.timestamp == pytest.approx(NS_TS / 1e9)

    def test_no_timestamp_uses_now(self):
        before = datetime.now(UTC).timestamp()
        q = quote_from_snapshot(snapshot("AAPL", prev=189.0))
        assert q.timestamp >= before

    def test_no_usable_price_returns_none(self):
        assert quote_from_snapshot(snapshot("AAPL", day=0)) is None
        assert quote_from_snapshot(snapshot("AAPL")) is None

    def test_missing_ticker_returns_none(self):
        assert quote_from_snapshot(snapshot("", last=1.0)) is None


@pytest.mark.asyncio
class TestSnapshotMode:
    async def test_start_does_immediate_poll(self):
        cache = PriceCache()
        client = FakeMassiveClient(
            snapshots=[snapshot("AAPL", last=190.5), snapshot("MSFT", last=420.0)]
        )
        source = _source(cache, client)
        await source.start(["AAPL", "MSFT"])
        try:
            assert cache.get_price("AAPL") == 190.5
            assert cache.get_price("MSFT") == 420.0
            assert cache.get("AAPL").timestamp == pytest.approx(NS_TS / 1e9)
            assert client.calls == [("snapshot", ("AAPL", "MSFT"))]
            assert source.mode == SNAPSHOT_MODE
        finally:
            await source.stop()

    async def test_one_request_per_poll_for_all_tickers(self):
        cache = PriceCache()
        tickers = ["AAPL", "MSFT", "NVDA", "TSLA"]
        client = FakeMassiveClient(snapshots=[snapshot(t, last=100.0) for t in tickers])
        source = _source(cache, client)
        source._tickers = list(tickers)
        await source._poll_once()
        assert client.calls == [("snapshot", tuple(tickers))]
        assert len(cache) == 4

    async def test_start_normalizes_and_dedupes(self):
        cache = PriceCache()
        client = FakeMassiveClient(snapshots=[snapshot("AAPL", last=190.5)])
        source = _source(cache, client)
        await source.start([" aapl ", "AAPL"])
        try:
            assert source.get_tickers() == ["AAPL"]
            assert cache.get_price("AAPL") == 190.5
        finally:
            await source.stop()

    async def test_poll_loop_repeats(self):
        cache = PriceCache()
        client = FakeMassiveClient(snapshots=[snapshot("AAPL", last=190.5)])
        source = _source(cache, client, poll_interval=0.01)
        await source.start(["AAPL"])
        await asyncio.sleep(0.08)
        await source.stop()
        assert len(client.calls) >= 3

    async def test_unknown_ticker_left_unpriced(self):
        cache = PriceCache()
        client = FakeMassiveClient(snapshots=[snapshot("AAPL", last=190.5)])
        source = _source(cache, client)
        source._tickers = ["AAPL", "ZZZZ"]
        await source._poll_once()
        assert cache.get_price("ZZZZ") is None
        assert cache.get_price("AAPL") == 190.5

    async def test_malformed_snapshot_skipped(self):
        class Broken:
            ticker = "BAD"

            @property
            def last_trade(self):
                raise TypeError("garbage")

        cache = PriceCache()
        client = FakeMassiveClient(snapshots=[snapshot("AAPL", last=190.5)])
        client.get_snapshot_all = lambda market_type, tickers=None, **kw: [
            snapshot("AAPL", last=190.5),
            Broken(),
        ]
        source = _source(cache, client)
        source._tickers = ["AAPL", "BAD"]
        await source._poll_once()
        assert cache.get_price("AAPL") == 190.5
        assert cache.get_price("BAD") is None

    async def test_api_error_keeps_last_prices_and_mode(self):
        cache = PriceCache()
        client = FakeMassiveClient(snapshots=[snapshot("AAPL", last=190.5)])
        source = _source(cache, client)
        source._tickers = ["AAPL"]
        await source._poll_once()
        client.snapshot_error = BAD_KEY
        await source._poll_once()  # must not raise
        assert source.mode == SNAPSHOT_MODE
        assert cache.get_price("AAPL") == 190.5

    async def test_network_error_does_not_crash(self):
        cache = PriceCache()
        client = FakeMassiveClient(snapshot_error=ConnectionError("network down"))
        source = _source(cache, client)
        source._tickers = ["AAPL"]
        await source._poll_once()
        assert len(cache) == 0

    async def test_repeated_error_logged_once_then_recovery(self, caplog):
        cache = PriceCache()
        client = FakeMassiveClient(snapshot_error=BAD_KEY)
        source = _source(cache, client)
        source._tickers = ["AAPL"]
        with caplog.at_level(logging.DEBUG, logger="app.market.massive_client"):
            for _ in range(3):
                await source._poll_once()
            client.snapshot_error = None
            client.snapshots = [snapshot("AAPL", last=1.0)]
            await source._poll_once()
        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(errors) == 1
        assert any("recovered" in r.getMessage() for r in caplog.records)

    async def test_empty_tickers_skips_poll(self):
        client = FakeMassiveClient()
        source = _source(PriceCache(), client)
        await source._poll_once()
        assert client.calls == []

    async def test_removed_during_inflight_poll_is_not_resurrected(self):
        cache = PriceCache()
        client = FakeMassiveClient(snapshots=[snapshot("AAPL", last=190.5)])
        source = _source(cache, client)
        source._tickers = ["AAPL"]

        real_fetch = source._fetch

        async def slow_fetch(tickers):
            quotes = await real_fetch(tickers)
            await source.remove_ticker("AAPL")  # user removes it mid-flight
            return quotes

        source._fetch = slow_fetch
        await source._poll_once()
        assert "AAPL" not in cache
        assert "AAPL" not in source.get_tickers()

    async def test_worker_thread_gets_a_copy_of_tickers(self):
        cache = PriceCache()
        seen: list = []
        client = FakeMassiveClient()

        def capture(market_type, tickers=None, **kw):
            seen.append(tickers)
            return []

        client.get_snapshot_all = capture
        source = _source(cache, client)
        source._tickers = ["AAPL"]
        await source._poll_once()
        assert seen[0] == ["AAPL"] and seen[0] is not source._tickers

    async def test_add_ticker_appears_on_next_poll(self):
        cache = PriceCache()
        client = FakeMassiveClient(
            snapshots=[snapshot("AAPL", last=1.0), snapshot("TSLA", last=2.0)]
        )
        source = _source(cache, client)
        await source.start(["AAPL"])
        try:
            await source.add_ticker("tsla")
            assert cache.get_price("TSLA") is None  # snapshot mode: next poll
            await source._poll_once()
            assert cache.get_price("TSLA") == 2.0
        finally:
            await source.stop()

    async def test_add_and_remove_normalize(self):
        cache = PriceCache()
        source = _source(cache, FakeMassiveClient())
        await source.add_ticker("  aapl ")
        await source.add_ticker("AAPL")
        assert source.get_tickers() == ["AAPL"]
        cache.update("AAPL", 1.0)
        await source.remove_ticker("aapl")
        assert source.get_tickers() == [] and "AAPL" not in cache

    async def test_stop_is_idempotent_and_cancels_task(self):
        source = _source(PriceCache(), FakeMassiveClient())
        await source.stop()  # before start
        await source.start(["AAPL"])
        task = source._task
        assert task is not None and not task.done()
        await source.stop()
        await source.stop()
        assert source._task is None and task.cancelled()

    async def test_constructs_real_client_when_none_injected(self, monkeypatch):
        from app.market import massive_client

        created = {}

        class StubClient(FakeMassiveClient):
            def __init__(self, api_key):
                super().__init__()
                created["key"] = api_key

        monkeypatch.setattr(massive_client, "RESTClient", StubClient)
        source = MassiveDataSource(api_key="abc", price_cache=PriceCache(), poll_interval=60)
        await source.start(["AAPL"])
        await source.stop()
        assert created == {"key": "abc"}


@pytest.mark.asyncio
class TestEodFallback:
    """Free Basic plan: snapshots are NOT_AUTHORIZED → grouped-daily closes."""

    async def test_not_authorized_switches_to_eod(self):
        cache = PriceCache()
        client = FakeMassiveClient(
            snapshot_error=NOT_AUTHORIZED,
            grouped={_yesterday(): [grouped_bar("AAPL", 189.0), grouped_bar("MSFT", 410.0)]},
        )
        source = _source(cache, client, eod_poll_interval=300.0)
        await source.start(["AAPL"])
        try:
            assert source.mode == EOD_MODE
            assert source.current_interval == 300.0
            assert cache.get_price("AAPL") == 189.0
            assert cache.get("AAPL").timestamp == MS_TS / 1e3
            assert "MSFT" not in cache  # only tracked tickers are written
        finally:
            await source.stop()

    async def test_walks_back_over_weekend(self):
        cache = PriceCache()
        client = FakeMassiveClient(
            snapshot_error=NOT_AUTHORIZED,
            grouped={_yesterday(3): [grouped_bar("AAPL", 187.0)]},
        )
        source = _source(cache, client)
        source._tickers = ["AAPL"]
        await source._poll_once()
        grouped_calls = [c for c in client.calls if c[0] == "grouped"]
        assert [c[1] for c in grouped_calls] == [_yesterday(1), _yesterday(2), _yesterday(3)]
        assert cache.get_price("AAPL") == 187.0

    async def test_gives_up_after_lookback_limit(self):
        cache = PriceCache()
        client = FakeMassiveClient(snapshot_error=NOT_AUTHORIZED)
        source = _source(cache, client)
        source._tickers = ["AAPL"]
        await source._poll_once()
        assert len([c for c in client.calls if c[0] == "grouped"]) == 5
        assert len(cache) == 0

    async def test_eod_table_is_reused_within_interval(self):
        cache = PriceCache()
        client = FakeMassiveClient(
            snapshot_error=NOT_AUTHORIZED,
            grouped={_yesterday(): [grouped_bar("AAPL", 189.0)]},
        )
        source = _source(cache, client, eod_poll_interval=300.0)
        source._tickers = ["AAPL"]
        await source._poll_once()
        await source._poll_once()
        assert [c[0] for c in client.calls] == ["snapshot", "grouped"]  # no second request

    async def test_eod_add_ticker_priced_immediately_from_table(self):
        cache = PriceCache()
        client = FakeMassiveClient(
            snapshot_error=NOT_AUTHORIZED,
            grouped={_yesterday(): [grouped_bar("AAPL", 189.0), grouped_bar("PYPL", 70.0)]},
        )
        source = _source(cache, client)
        await source.start(["AAPL"])
        try:
            await source.add_ticker("PYPL")
            assert cache.get_price("PYPL") == 70.0
        finally:
            await source.stop()

    async def test_other_bad_response_does_not_switch(self):
        client = FakeMassiveClient(snapshot_error=BAD_KEY)
        source = _source(PriceCache(), client)
        source._tickers = ["AAPL"]
        await source._poll_once()
        assert source.mode == SNAPSHOT_MODE
        assert all(c[0] == "snapshot" for c in client.calls)
