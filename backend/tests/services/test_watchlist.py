"""Watchlist service rules: normalization, cap, tracked-tickers set."""

from __future__ import annotations

import pytest

from app.services import (
    MAX_WATCHLIST,
    ServiceError,
    add_ticker,
    execute_trade,
    list_watchlist,
    normalize_ticker,
    remove_ticker,
    tracked_tickers,
)

DEFAULTS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]


@pytest.mark.parametrize("raw,expected", [("aapl", "AAPL"), (" brk.b ", "BRK.B"), ("V", "V")])
def test_normalize_valid(raw, expected):
    assert normalize_ticker(raw) == expected


@pytest.mark.parametrize("raw", ["", "1ABC", "TOOLONG", ".AB", "AB-C", "A B", None, 5])
def test_normalize_invalid(raw):
    with pytest.raises(ServiceError) as ei:
        normalize_ticker(raw)
    assert ei.value.status_code == 422


async def test_default_watchlist(source):
    items = list_watchlist()
    assert [i["ticker"] for i in items] == DEFAULTS
    first = items[0]
    assert set(first) == {"ticker", "price", "previous_price", "session_change_percent", "added_at"}
    assert first["price"] == 190.0
    assert first["session_change_percent"] == 0.0


async def test_session_change_in_watchlist(source, cache):
    cache.update("AAPL", 199.5)
    item = list_watchlist()[0]
    assert item["price"] == 199.5
    assert item["previous_price"] == 190.0
    assert item["session_change_percent"] == 5.0


async def test_add_ticker(source):
    entry = await add_ticker("pypl")
    assert entry["ticker"] == "PYPL"
    assert entry["price"] == 60.0
    assert entry["added_at"].endswith("Z")
    assert list_watchlist()[-1]["ticker"] == "PYPL"
    assert "PYPL" in source.get_tickers()


async def test_add_ticker_without_price(source):
    entry = await add_ticker("ZZZ")
    assert entry["price"] is None
    assert entry["previous_price"] is None
    assert entry["session_change_percent"] is None


async def test_add_duplicate(source):
    with pytest.raises(ServiceError) as ei:
        await add_ticker("aapl")
    assert ei.value.status_code == 409
    assert ei.value.detail == "AAPL is already on the watchlist"


async def test_watchlist_cap(source):
    for i in range(MAX_WATCHLIST - len(DEFAULTS)):
        await add_ticker("Q" + "ABCDEFGHIJKLMNOPQRST"[i])
    with pytest.raises(ServiceError) as ei:
        await add_ticker("PYPL")
    assert ei.value.status_code == 400
    assert "full" in ei.value.detail


async def test_remove_ticker(source):
    await remove_ticker("googl")
    assert "GOOGL" not in [i["ticker"] for i in list_watchlist()]
    assert "GOOGL" not in source.get_tickers()


async def test_remove_missing(source):
    with pytest.raises(ServiceError) as ei:
        await remove_ticker("PYPL")
    assert ei.value.status_code == 404


async def test_remove_with_open_position_keeps_tracking(source):
    await execute_trade("TSLA", "buy", 1)
    await remove_ticker("TSLA")
    assert "TSLA" not in [i["ticker"] for i in list_watchlist()]
    assert "TSLA" in source.get_tickers()
    assert "TSLA" in tracked_tickers()
    assert source.cache.get_price("TSLA") == 250.0


async def test_tracked_tickers_union(source):
    await execute_trade("TSLA", "buy", 1)
    await remove_ticker("TSLA")
    await remove_ticker("AAPL")
    tracked = tracked_tickers()
    assert "TSLA" in tracked
    assert "AAPL" not in tracked
    assert len(tracked) == len(set(tracked)) == 9
