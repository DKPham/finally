"""FastAPI application entry point: `uvicorn app.main:app`."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import db, services
from app.api import health, portfolio, watchlist
from app.market import PriceCache, create_market_data_source, create_stream_router
from app.services import ServiceError, state

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
SNAPSHOT_INTERVAL = 30.0  # seconds

load_dotenv(PROJECT_ROOT / ".env", override=False)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

try:
    from app.api import chat as chat_api
except ImportError as e:  # pragma: no cover - only while the chat module is missing
    logger.warning("Chat API unavailable: %s", e)
    chat_api = None


async def _snapshot_loop(interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            services.record_snapshot()
        except Exception:
            logger.exception("Portfolio snapshot failed")


def _static_dir() -> Path | None:
    for candidate in (BACKEND_DIR / "static", PROJECT_ROOT / "frontend" / "out"):
        if candidate.is_dir():
            return candidate
    return None


def create_app() -> FastAPI:
    """Build the app. Each app gets its own PriceCache (handy for tests)."""
    cache = PriceCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db.init_db()
        state.price_cache = cache
        source = create_market_data_source(cache)
        state.market_source = source
        tickers = services.tracked_tickers()
        await source.start(tickers)
        logger.info("Market data source started with %d tickers", len(tickers))
        services.record_snapshot()
        task = asyncio.create_task(_snapshot_loop(SNAPSHOT_INTERVAL), name="snapshots")
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await source.stop()
            state.market_source = None

    app = FastAPI(title="FinAlly", lifespan=lifespan)

    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    app.include_router(health.router)
    app.include_router(portfolio.router)
    app.include_router(watchlist.router)
    app.include_router(create_stream_router(cache))
    if chat_api is not None:
        app.include_router(chat_api.router)

    static = _static_dir()
    if static is not None:
        app.mount("/", StaticFiles(directory=static, html=True), name="static")
    else:
        logger.info("No frontend build found; serving API only")
    return app


app = create_app()
