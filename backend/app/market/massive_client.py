"""Massive (Polygon.io) REST poller for real market data.

Two modes:
  * snapshot (initial): GET /v2/snapshot/locale/us/markets/stocks/tickers — one call
    for every tracked ticker, real-time or 15-min delayed depending on the plan.
  * eod (fallback): the free Basic plan has no snapshot access (403 NOT_AUTHORIZED).
    On that error the source switches permanently to the grouped-daily endpoint,
    which returns the last trading day's close for the whole market in one call.

See planning/MASSIVE_API.md for endpoint and SDK details.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

from massive import RESTClient
from massive.exceptions import BadResponse
from massive.rest.models import SnapshotMarketType

from .cache import PriceCache
from .interface import MarketDataSource

logger = logging.getLogger(__name__)

SNAPSHOT_MODE = "snapshot"
EOD_MODE = "eod"
EOD_MAX_LOOKBACK_DAYS = 5  # covers a long weekend plus a holiday


class Quote(NamedTuple):
    """A price extracted from a Massive response."""

    ticker: str
    price: float
    timestamp: float  # Unix seconds


def _first_positive(*values: float | None) -> float | None:
    for value in values:
        if value is not None and value > 0:
            return float(value)
    return None


def quote_from_snapshot(snap: Any) -> Quote | None:
    """Extract a Quote from a massive ``TickerSnapshot``. Returns None if unusable.

    Price fallback chain: last_trade.price → min.close → day.close → prev_day.close
    (day.close is 0 right after the daily reset; last_trade is absent on plans
    without trades). Timestamps: last_trade.sip_timestamp or snapshot.updated, both
    in nanoseconds.
    """
    if not snap.ticker:
        return None
    last_trade = snap.last_trade
    price = _first_positive(
        last_trade.price if last_trade else None,
        snap.min.close if snap.min else None,
        snap.day.close if snap.day else None,
        snap.prev_day.close if snap.prev_day else None,
    )
    if price is None:
        return None
    ns = (last_trade.sip_timestamp if last_trade else None) or snap.updated
    timestamp = ns / 1e9 if ns else time.time()
    return Quote(snap.ticker, price, timestamp)


def _is_not_authorized(err: BadResponse) -> bool:
    return "NOT_AUTHORIZED" in str(err)


def _normalize(ticker: str) -> str:
    return ticker.upper().strip()


class MassiveDataSource(MarketDataSource):
    """MarketDataSource backed by the Massive (Polygon.io) REST API.

    Rate limits: free tier allows 5 req/min, so the default 15 s poll interval
    is safe. Paid tiers can poll every 2-5 s.
    """

    def __init__(
        self,
        api_key: str,
        price_cache: PriceCache,
        poll_interval: float = 15.0,
        eod_poll_interval: float = 300.0,
        client: Any | None = None,  # injectable for tests
    ) -> None:
        self._api_key = api_key
        self._cache = price_cache
        self._interval = poll_interval
        self._eod_interval = eod_poll_interval
        self._client = client
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None
        self._mode = SNAPSHOT_MODE
        # EOD mode keeps the whole market's latest closes so a ticker added later
        # can be priced without spending another request.
        self._eod_quotes: dict[str, Quote] = {}
        self._eod_fetched_at = 0.0
        self._last_error: str | None = None

    # --- MarketDataSource interface ---

    async def start(self, tickers: list[str]) -> None:
        if self._client is None:
            self._client = RESTClient(api_key=self._api_key)
        self._tickers = list(dict.fromkeys(_normalize(t) for t in tickers))

        # Immediate first poll so the cache has data right away (best effort)
        await self._poll_once()

        self._task = asyncio.create_task(self._poll_loop(), name="massive-poller")
        logger.info(
            "Massive poller started: %d tickers, mode=%s, %.1fs interval",
            len(self._tickers),
            self._mode,
            self.current_interval,
        )

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Massive poller stopped")

    async def add_ticker(self, ticker: str) -> None:
        ticker = _normalize(ticker)
        if ticker in self._tickers:
            return
        self._tickers.append(ticker)
        # In EOD mode we may already hold its close — publish it right away
        quote = self._eod_quotes.get(ticker)
        if quote is not None:
            self._cache.update(quote.ticker, quote.price, quote.timestamp)
        logger.info("Massive: added ticker %s (mode=%s)", ticker, self._mode)

    async def remove_ticker(self, ticker: str) -> None:
        ticker = _normalize(ticker)
        self._tickers = [t for t in self._tickers if t != ticker]
        self._cache.remove(ticker)
        logger.info("Massive: removed ticker %s", ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    # --- Polling ---

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def current_interval(self) -> float:
        return self._interval if self._mode == SNAPSHOT_MODE else self._eod_interval

    async def _poll_loop(self) -> None:
        """Poll on interval. The first poll already happened in start()."""
        while True:
            await asyncio.sleep(self.current_interval)
            await self._poll_once()

    async def _poll_once(self) -> None:
        """One poll cycle: fetch, then write still-tracked tickers. Never raises."""
        if not self._tickers or self._client is None:
            return
        tickers = list(self._tickers)  # the worker thread must not see list mutations
        try:
            quotes = await self._fetch(tickers)
        except Exception as e:  # network, 401, 429 after SDK retries, parse errors
            self._log_failure(e)
            return

        # remove_ticker() may have run while we awaited the HTTP call; don't
        # resurrect a ticker that is no longer tracked.
        tracked = set(self._tickers)
        written = 0
        for quote in quotes:
            if quote.ticker in tracked:
                self._cache.update(quote.ticker, quote.price, quote.timestamp)
                written += 1

        if self._last_error is not None:
            logger.info("Massive poll recovered")
            self._last_error = None
        logger.debug("Massive poll (%s): updated %d/%d tickers", self._mode, written, len(tickers))

    async def _fetch(self, tickers: list[str]) -> list[Quote]:
        if self._mode == SNAPSHOT_MODE:
            try:
                return await asyncio.to_thread(self._fetch_snapshot_quotes, tickers)
            except BadResponse as e:
                if not _is_not_authorized(e):
                    raise
                logger.warning(
                    "Massive plan has no snapshot access; switching to end-of-day prices "
                    "(polling every %.0fs)",
                    self._eod_interval,
                )
                self._mode = EOD_MODE
        return await self._fetch_eod(tickers)

    def _fetch_snapshot_quotes(self, tickers: list[str]) -> list[Quote]:
        """Synchronous snapshot call. Runs in a worker thread."""
        snapshots = self._client.get_snapshot_all(
            market_type=SnapshotMarketType.STOCKS,
            tickers=tickers,
        )
        quotes: list[Quote] = []
        for snap in snapshots:
            try:
                quote = quote_from_snapshot(snap)
            except (AttributeError, TypeError, ValueError) as e:
                logger.warning(
                    "Skipping malformed snapshot for %s: %s", getattr(snap, "ticker", "???"), e
                )
                continue
            if quote is not None:
                quotes.append(quote)
        return quotes

    async def _fetch_eod(self, tickers: list[str]) -> list[Quote]:
        # Refresh the whole-market close table at most once per EOD interval
        stale = time.monotonic() - self._eod_fetched_at >= self._eod_interval
        if not self._eod_quotes or stale:
            self._eod_quotes = await asyncio.to_thread(self._fetch_latest_grouped_daily)
            self._eod_fetched_at = time.monotonic()
        return [self._eod_quotes[t] for t in tickers if t in self._eod_quotes]

    def _fetch_latest_grouped_daily(self) -> dict[str, Quote]:
        """Walk back from yesterday (UTC) to the last day with data. Worker thread."""
        day = datetime.now(UTC).date() - timedelta(days=1)
        for _ in range(EOD_MAX_LOOKBACK_DAYS):
            bars = self._client.get_grouped_daily_aggs(day.isoformat(), adjusted=True)
            if bars:
                return {
                    bar.ticker: Quote(
                        bar.ticker,
                        float(bar.close),
                        bar.timestamp / 1e3 if bar.timestamp else time.time(),
                    )
                    for bar in bars
                    if bar.ticker and bar.close
                }
            day -= timedelta(days=1)
        logger.warning("Massive: no grouped-daily data in the last %d days", EOD_MAX_LOOKBACK_DAYS)
        return {}

    def _log_failure(self, e: Exception) -> None:
        """Log a poll failure once at ERROR; repeats of the same error go to DEBUG."""
        message = f"{type(e).__name__}: {e}"
        if message != self._last_error:
            logger.error("Massive poll failed: %s", message)
            self._last_error = message
        else:
            logger.debug("Massive poll failed again: %s", message)
