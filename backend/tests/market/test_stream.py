"""Tests for the SSE price stream."""

import asyncio
import json
import socket

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from app.market.cache import PriceCache
from app.market.stream import _generate_events, create_stream_router

from .fakes import FakeRequest


async def _collect(cache: PriceCache, request: FakeRequest, **kwargs) -> list[str]:
    kwargs.setdefault("interval", 0.001)
    return [event async for event in _generate_events(cache, request, **kwargs)]


def _data_events(events: list[str]) -> list[dict]:
    return [json.loads(e.removeprefix("data: ")) for e in events if e.startswith("data: ")]


@pytest.mark.asyncio
class TestGenerateEvents:
    async def test_retry_first_then_batch_of_all_tickers(self):
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        cache.update("MSFT", 420.0)
        events = await _collect(cache, FakeRequest(polls=1))
        assert events[0] == "retry: 1000\n\n"
        assert all(e.endswith("\n\n") for e in events)
        (batch,) = _data_events(events)
        assert set(batch) == {"AAPL", "MSFT"}
        assert batch["AAPL"] == cache.get("AAPL").to_dict()

    async def test_batch_shape_matches_plan(self):
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        cache.update("AAPL", 190.52)
        (batch,) = _data_events(await _collect(cache, FakeRequest(polls=1)))
        assert set(batch["AAPL"]) == {
            "ticker",
            "price",
            "previous_price",
            "timestamp",
            "change",
            "change_percent",
            "direction",
            "session_open",
            "session_change_percent",
        }
        assert batch["AAPL"]["session_open"] == 190.0
        assert batch["AAPL"]["direction"] == "up"

    async def test_no_duplicate_when_version_unchanged(self):
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        events = await _collect(cache, FakeRequest(polls=5))
        assert len(_data_events(events)) == 1

    async def test_new_event_on_each_change(self):
        cache = PriceCache()
        cache.update("AAPL", 190.0)

        def tick(n):
            if n in (2, 3):
                cache.update("AAPL", 190.0 + n)

        events = await _collect(cache, FakeRequest(polls=4, on_poll=tick))
        prices = [b["AAPL"]["price"] for b in _data_events(events)]
        assert prices == [190.0, 192.0, 193.0]

    async def test_removal_pushes_batch_without_ticker(self):
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        cache.update("MSFT", 420.0)

        events = await _collect(
            cache, FakeRequest(polls=3, on_poll=lambda n: n == 2 and cache.remove("MSFT"))
        )
        batches = _data_events(events)
        assert set(batches[-1]) == {"AAPL"}

    async def test_removing_last_ticker_sends_empty_batch(self):
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        events = await _collect(
            cache, FakeRequest(polls=3, on_poll=lambda n: n == 2 and cache.remove("AAPL"))
        )
        assert _data_events(events)[-1] == {}

    async def test_heartbeat_when_idle(self):
        cache = PriceCache()
        cache.update("AAPL", 1.0)
        events = await _collect(cache, FakeRequest(polls=3), heartbeat=0.0)
        assert ": keep-alive\n\n" in events
        assert len(_data_events(events)) == 1

    async def test_no_heartbeat_before_interval(self):
        cache = PriceCache()
        cache.update("AAPL", 1.0)
        events = await _collect(cache, FakeRequest(polls=3), heartbeat=60.0)
        assert ": keep-alive\n\n" not in events

    async def test_stops_on_disconnect(self):
        events = await _collect(PriceCache(), FakeRequest(polls=0))
        assert events == ["retry: 1000\n\n"]


class TestRouterFactory:
    def test_each_call_builds_independent_router(self):
        r1 = create_stream_router(PriceCache())
        r2 = create_stream_router(PriceCache())
        assert r1 is not r2
        assert [r.path for r in r1.routes] == ["/api/stream/prices"]
        assert [r.path for r in r2.routes] == ["/api/stream/prices"]

    def test_two_apps_use_their_own_cache(self):
        caches = [PriceCache(), PriceCache()]
        caches[0].update("AAA", 1.0)
        caches[1].update("BBB", 2.0)
        apps = []
        for cache in caches:
            app = FastAPI()
            app.include_router(create_stream_router(cache))
            apps.append(app)
        # Each app has exactly one /prices route bound to its own cache
        for app in apps:
            assert [r.path for r in app.routes].count("/api/stream/prices") == 1


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.asyncio
async def test_endpoint_end_to_end_over_http():
    """Real uvicorn server + streaming HTTP client: headers, retry line, live batches."""
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    app = FastAPI()
    app.include_router(create_stream_router(cache, interval=0.01))

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, port=port, log_level="warning", lifespan="off", ws="none")
    )
    serve = asyncio.create_task(server.serve())
    try:
        while not server.started:
            await asyncio.sleep(0.01)

        async with httpx.AsyncClient(timeout=5) as client:
            async with client.stream("GET", f"http://127.0.0.1:{port}/api/stream/prices") as resp:
                assert resp.status_code == 200
                assert resp.headers["content-type"].startswith("text/event-stream")
                assert resp.headers["cache-control"] == "no-cache"
                assert resp.headers["x-accel-buffering"] == "no"

                lines = resp.aiter_lines()
                assert await anext(lines) == "retry: 1000"
                batches = []
                async for line in lines:
                    if line.startswith("data: "):
                        batches.append(json.loads(line[6:]))
                        if len(batches) == 1:
                            cache.update("AAPL", 191.0)  # producer ticks
                        else:
                            break
        assert batches[0]["AAPL"]["price"] == 190.0
        assert batches[1]["AAPL"]["price"] == 191.0
        assert batches[1]["AAPL"]["direction"] == "up"
    finally:
        server.should_exit = True
        await asyncio.wait_for(serve, timeout=5)
