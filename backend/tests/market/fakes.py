"""Test doubles for the market data tests.

Massive fixtures are built from the real SDK models via ``from_dict`` on raw API
JSON, never ``MagicMock``: a permissive mock happily answers a wrong attribute
name (that is how a ``last_trade.timestamp`` bug once went unnoticed).
"""

from __future__ import annotations

from massive.rest.models import GroupedDailyAgg, TickerSnapshot

# 2024-11-16T10:40:00.123456789Z in nanoseconds (snapshot `lastTrade.t` / `updated`)
NS_TS = 1_731_753_600_123_456_789
# Aggregate bar timestamp in milliseconds
MS_TS = 1_731_704_400_000


def snapshot(
    ticker: str,
    last: float | None = None,
    ns: int | None = NS_TS,
    minute: float | None = None,
    day: float | None = None,
    prev: float | None = None,
    updated: int | None = None,
) -> TickerSnapshot:
    """Build a real TickerSnapshot from raw-API-shaped JSON."""
    raw: dict = {"ticker": ticker}
    if last is not None:
        raw["lastTrade"] = {"p": last, "s": 100, "t": ns, "x": 4}
    if minute is not None:
        raw["min"] = {"c": minute, "t": MS_TS}
    if day is not None:
        raw["day"] = {"c": day}
    if prev is not None:
        raw["prevDay"] = {"c": prev}
    if updated is not None:
        raw["updated"] = updated
    return TickerSnapshot.from_dict(raw)


def grouped_bar(ticker: str, close: float, ts_ms: int | None = MS_TS) -> GroupedDailyAgg:
    """Build a real GroupedDailyAgg from raw-API-shaped JSON."""
    raw = {"T": ticker, "o": close, "h": close, "l": close, "c": close, "v": 1000}
    if ts_ms is not None:
        raw["t"] = ts_ms
    return GroupedDailyAgg.from_dict(raw)


class FakeMassiveClient:
    """Stands in for massive.RESTClient. Records calls; no network."""

    def __init__(
        self,
        snapshots: list[TickerSnapshot] | None = None,
        snapshot_error: Exception | None = None,
        grouped: dict[str, list[GroupedDailyAgg]] | None = None,
    ) -> None:
        self.snapshots = snapshots or []
        self.snapshot_error = snapshot_error
        self.grouped = grouped or {}  # {"YYYY-MM-DD": [bars]}
        self.calls: list[tuple] = []

    def get_snapshot_all(self, market_type, tickers=None, **kwargs):
        self.calls.append(("snapshot", tuple(tickers or ())))
        if self.snapshot_error is not None:
            raise self.snapshot_error
        wanted = set(tickers or ())
        # Like the real API: unknown tickers are silently omitted
        return [s for s in self.snapshots if s.ticker in wanted]

    def get_grouped_daily_aggs(self, date, adjusted=None, **kwargs):
        self.calls.append(("grouped", date))
        return list(self.grouped.get(date, []))


class FakeRequest:
    """Minimal stand-in for starlette's Request in SSE generator tests."""

    client = None

    def __init__(self, polls: int, on_poll=None) -> None:
        self._remaining = polls
        self._count = 0
        self._on_poll = on_poll

    async def is_disconnected(self) -> bool:
        self._count += 1
        if self._on_poll is not None:
            self._on_poll(self._count)
        self._remaining -= 1
        return self._remaining < 0
