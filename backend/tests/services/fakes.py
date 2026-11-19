"""Deterministic in-memory MarketDataSource for service/API tests."""

from __future__ import annotations

from app.market import MarketDataSource, PriceCache


class FakeSource(MarketDataSource):
    """Seeds fixed prices into the cache; no background loop.

    `prices` maps ticker -> price for tickers that get a price on add/start;
    others get none (simulating a Massive ticker not polled yet).
    """

    def __init__(self, cache: PriceCache, prices: dict[str, float] | None = None) -> None:
        self.cache = cache
        self.prices = dict(prices or {})
        self.tickers: list[str] = []
        self.started = False
        self.stopped = False

    async def start(self, tickers: list[str]) -> None:
        self.started = True
        for t in tickers:
            await self.add_ticker(t)

    async def stop(self) -> None:
        self.stopped = True

    async def add_ticker(self, ticker: str) -> None:
        if ticker not in self.tickers:
            self.tickers.append(ticker)
            if ticker in self.prices:
                self.cache.update(ticker, self.prices[ticker])

    async def remove_ticker(self, ticker: str) -> None:
        self.tickers = [t for t in self.tickers if t != ticker]
        self.cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return list(self.tickers)


DEFAULT_PRICES = {
    "AAPL": 190.0, "GOOGL": 175.0, "MSFT": 420.0, "AMZN": 185.0, "TSLA": 250.0,
    "NVDA": 800.0, "META": 500.0, "JPM": 200.0, "V": 280.0, "NFLX": 600.0,
    "PYPL": 60.0,
}
