"""SSE generator emits retry, then batches including session fields."""

import json

from app.market.cache import PriceCache
from app.market.stream import _generate_events, create_stream_router


class FakeRequest:
    client = None

    def __init__(self, polls: int) -> None:
        self._polls = polls

    async def is_disconnected(self) -> bool:
        self._polls -= 1
        return self._polls < 0


async def test_stream_events():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    cache.update("AAPL", 190.52)
    events = [e async for e in _generate_events(cache, FakeRequest(polls=2), interval=0)]
    assert events[0] == "retry: 1000\n\n"
    assert len(events) == 2  # second poll: version unchanged, nothing emitted
    payload = json.loads(events[1].removeprefix("data: ").strip())
    aapl = payload["AAPL"]
    assert aapl["session_open"] == 190.0
    assert aapl["session_change_percent"] == 0.2737
    assert aapl["previous_price"] == 190.0


def test_router_factory_is_independent():
    r1 = create_stream_router(PriceCache())
    r2 = create_stream_router(PriceCache())
    assert r1 is not r2
    assert len(r1.routes) == len(r2.routes) == 1
