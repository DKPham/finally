"""SSE streaming endpoint for live price updates."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

logger = logging.getLogger(__name__)


def create_stream_router(
    price_cache: PriceCache,
    interval: float = 0.5,
    heartbeat: float = 15.0,
) -> APIRouter:
    """Create the SSE router bound to a price cache.

    A fresh APIRouter is built per call, so building several apps (e.g. in tests)
    never registers /prices twice on a shared router.
    """
    router = APIRouter(prefix="/api/stream", tags=["streaming"])

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        """SSE endpoint: one event per cache change, each a batch of all tracked tickers.

            data: {"AAPL": {"ticker": "AAPL", "price": 190.50, ...}, ...}

        Starts with a retry directive so EventSource reconnects after 1 s.
        """
        return StreamingResponse(
            _generate_events(price_cache, request, interval, heartbeat),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering if proxied
            },
        )

    return router


async def _generate_events(
    price_cache: PriceCache,
    request: Request,
    interval: float = 0.5,
    heartbeat: float = 15.0,
) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted events until the client disconnects.

    - Emits a batch whenever the cache version changes. The batch may be ``{}``
      when nothing is tracked, so clients (which replace their price map on each
      event) drop removed tickers.
    - Emits a ``: keep-alive`` comment after ``heartbeat`` seconds of silence so
      idle proxies keep the connection open (e.g. Massive end-of-day mode).
    """
    yield "retry: 1000\n\n"

    client = request.client.host if request.client else "unknown"
    logger.info("SSE client connected: %s", client)
    last_version = -1
    last_sent = time.monotonic()
    try:
        while not await request.is_disconnected():
            version = price_cache.version
            if version != last_version:
                last_version = version
                batch = {t: u.to_dict() for t, u in price_cache.get_all().items()}
                yield f"data: {json.dumps(batch)}\n\n"
                last_sent = time.monotonic()
            elif time.monotonic() - last_sent >= heartbeat:
                yield ": keep-alive\n\n"
                last_sent = time.monotonic()
            await asyncio.sleep(interval)
    finally:
        # Runs on disconnect and on cancellation; cancellation still propagates.
        logger.info("SSE client disconnected: %s", client)
