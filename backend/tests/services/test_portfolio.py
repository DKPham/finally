"""Trade execution and valuation rules (PLAN §9)."""

from __future__ import annotations

import pytest

from app import db
from app.services import (
    ServiceError,
    execute_trade,
    get_history,
    get_portfolio,
    list_watchlist,
    record_snapshot,
    remove_ticker,
)


def _cash() -> float:
    with db.transaction() as conn:
        return db.get_cash(conn)


def _trades() -> list[dict]:
    with db.transaction() as conn:
        return db.list_trades(conn)


async def test_fresh_portfolio(source):
    p = get_portfolio()
    assert p == {
        "cash_balance": 10000.0,
        "positions_value": 0.0,
        "total_value": 10000.0,
        "unrealized_pnl": 0.0,
        "positions": [],
    }


async def test_buy_creates_position_and_debits_cash(source):
    result = await execute_trade("AAPL", "buy", 10)
    trade = result["trade"]
    assert trade["ticker"] == "AAPL"
    assert trade["side"] == "buy"
    assert trade["quantity"] == 10
    assert trade["price"] == 190.0
    assert trade["id"] and trade["executed_at"].endswith("Z")
    p = result["portfolio"]
    assert p["cash_balance"] == 8100.0
    assert p["positions"] == [
        {"ticker": "AAPL", "quantity": 10, "avg_cost": 190.0, "current_price": 190.0,
         "market_value": 1900.0, "unrealized_pnl": 0.0, "unrealized_pnl_percent": 0.0}
    ]
    assert p["total_value"] == 10000.0


async def test_weighted_average_cost(source, cache):
    await execute_trade("AAPL", "buy", 10)
    cache.update("AAPL", 200.0)
    result = await execute_trade("AAPL", "buy", 30)
    pos = result["portfolio"]["positions"][0]
    assert pos["quantity"] == 40
    assert pos["avg_cost"] == pytest.approx((10 * 190 + 30 * 200) / 40)
    assert _cash() == pytest.approx(10000 - 1900 - 6000)


async def test_unrealized_pnl(source, cache):
    await execute_trade("AAPL", "buy", 10)
    cache.update("AAPL", 209.0)
    p = get_portfolio()
    pos = p["positions"][0]
    assert pos["current_price"] == 209.0
    assert pos["market_value"] == 2090.0
    assert pos["unrealized_pnl"] == 190.0
    assert pos["unrealized_pnl_percent"] == 10.0
    assert p["unrealized_pnl"] == 190.0
    assert p["positions_value"] == 2090.0
    assert p["total_value"] == 8100.0 + 2090.0


async def test_current_price_falls_back_to_avg_cost(source, cache):
    await execute_trade("AAPL", "buy", 10)
    cache.remove("AAPL")
    pos = get_portfolio()["positions"][0]
    assert pos["current_price"] == 190.0
    assert pos["unrealized_pnl"] == 0.0


async def test_insufficient_cash(source):
    with pytest.raises(ServiceError) as ei:
        await execute_trade("NVDA", "buy", 13)  # 13 * 800 = 10400
    assert ei.value.status_code == 400
    assert ei.value.detail == "Insufficient cash: need $10,400.00, have $10,000.00"
    assert _cash() == 10000.0
    assert _trades() == []


async def test_buy_exactly_all_cash(source):
    await execute_trade("NVDA", "buy", 12.5)  # exactly $10,000
    assert _cash() == pytest.approx(0.0)


async def test_sell_partial_keeps_avg_cost(source, cache):
    await execute_trade("AAPL", "buy", 10)
    cache.update("AAPL", 200.0)
    result = await execute_trade("AAPL", "sell", 4)
    pos = result["portfolio"]["positions"][0]
    assert pos["quantity"] == 6
    assert pos["avg_cost"] == 190.0
    assert _cash() == pytest.approx(8100 + 800)


async def test_sell_at_loss(source, cache):
    await execute_trade("TSLA", "buy", 10)
    cache.update("TSLA", 200.0)
    result = await execute_trade("TSLA", "sell", 10)
    assert result["portfolio"]["cash_balance"] == 10000 - 2500 + 2000
    assert result["portfolio"]["positions"] == []


async def test_sell_full_position_deletes_row(source):
    await execute_trade("AAPL", "buy", 10)
    await execute_trade("AAPL", "sell", 10)
    with db.transaction() as conn:
        assert db.get_position(conn, "AAPL") is None
    assert _cash() == pytest.approx(10000.0)


async def test_sell_all_within_tolerance(source):
    await execute_trade("AAPL", "buy", 1.2345)
    # 1.2345005 rounds to 1.2345 anyway; held + tiny excess is still "sell all"
    await execute_trade("AAPL", "sell", 1.2345)
    assert get_portfolio()["positions"] == []
    assert _cash() == pytest.approx(10000.0)


async def test_sell_more_than_owned(source):
    await execute_trade("TSLA", "buy", 20)
    with pytest.raises(ServiceError) as ei:
        await execute_trade("TSLA", "sell", 100)
    assert ei.value.status_code == 400
    assert ei.value.detail == "Insufficient shares: you hold 20 TSLA, tried to sell 100"
    assert get_portfolio()["positions"][0]["quantity"] == 20


async def test_sell_without_position(source):
    with pytest.raises(ServiceError) as ei:
        await execute_trade("AAPL", "sell", 1)
    assert ei.value.status_code == 400
    assert "you hold 0 AAPL" in ei.value.detail


async def test_fractional_rounding(source):
    result = await execute_trade("AAPL", "buy", 0.123456789)
    assert result["trade"]["quantity"] == 0.1235
    assert result["portfolio"]["positions"][0]["quantity"] == 0.1235


@pytest.mark.parametrize("qty", [0.00001, 0.00004])
async def test_quantity_below_minimum(source, qty):
    with pytest.raises(ServiceError) as ei:
        await execute_trade("AAPL", "buy", qty)
    assert ei.value.status_code == 400


@pytest.mark.parametrize("qty", [0, -1, float("nan"), float("inf")])
async def test_non_positive_quantity(source, qty):
    with pytest.raises(ServiceError) as ei:
        await execute_trade("AAPL", "buy", qty)
    assert ei.value.status_code == 422


async def test_invalid_side(source):
    with pytest.raises(ServiceError) as ei:
        await execute_trade("AAPL", "short", 1)
    assert ei.value.status_code == 422


async def test_ticker_normalized(source):
    result = await execute_trade("  aapl ", "BUY", 1)
    assert result["trade"]["ticker"] == "AAPL"
    assert result["trade"]["side"] == "buy"


async def test_no_price_available(source):
    # ZZZ has no price in the fake source (like Massive before the next poll)
    with pytest.raises(ServiceError) as ei:
        await execute_trade("ZZZ", "buy", 1)
    assert ei.value.status_code == 400
    assert ei.value.detail == "No price available for ZZZ yet"
    # ...but it was still added to the watchlist so the user can retry
    assert "ZZZ" in [w["ticker"] for w in list_watchlist()]
    assert "ZZZ" in source.get_tickers()


async def test_trade_unwatched_ticker_adds_to_watchlist(source):
    result = await execute_trade("PYPL", "buy", 2)
    assert result["trade"]["price"] == 60.0
    assert [w["ticker"] for w in list_watchlist()][-1] == "PYPL"
    assert "PYPL" in source.get_tickers()


async def test_trade_with_full_watchlist_still_executes(source):
    from app.services import add_ticker

    for i in range(20):
        await add_ticker("X" + "ABCDEFGHIJKLMNOPQRST"[i])
    assert len(list_watchlist()) == 30
    result = await execute_trade("PYPL", "buy", 1)
    assert result["trade"]["ticker"] == "PYPL"
    assert "PYPL" not in [w["ticker"] for w in list_watchlist()]
    assert "PYPL" in source.get_tickers()  # tracked via the open position
    await execute_trade("PYPL", "sell", 1)
    assert "PYPL" not in source.get_tickers()


async def test_failed_trade_with_full_watchlist_untracks(source):
    from app.services import add_ticker

    for i in range(20):
        await add_ticker("X" + "ABCDEFGHIJKLMNOPQRST"[i])
    with pytest.raises(ServiceError):
        await execute_trade("PYPL", "sell", 1)
    assert "PYPL" not in source.get_tickers()


async def test_selling_unwatched_ticker_rewatches_it(source):
    await execute_trade("AAPL", "buy", 5)
    await remove_ticker("AAPL")
    assert "AAPL" in source.get_tickers()  # still held
    await execute_trade("AAPL", "sell", 5)
    # Selling re-adds AAPL to the watchlist first (trading an unwatched ticker), so it stays
    assert "AAPL" in [w["ticker"] for w in list_watchlist()]
    assert "AAPL" in source.get_tickers()


async def test_trade_records_snapshot_in_transaction(source):
    assert get_history() == []
    await execute_trade("AAPL", "buy", 1)
    history = get_history()
    assert len(history) == 1
    assert history[0]["total_value"] == 10000.0


async def test_failed_trade_writes_nothing(source):
    with pytest.raises(ServiceError):
        await execute_trade("AAPL", "buy", 1000)
    assert get_history() == []
    assert _trades() == []


async def test_sequential_trades_validate_against_prior_state(source):
    await execute_trade("NVDA", "buy", 10)  # $8,000
    with pytest.raises(ServiceError) as ei:
        await execute_trade("NVDA", "buy", 3)  # $2,400 > $2,000
    assert ei.value.detail == "Insufficient cash: need $2,400.00, have $2,000.00"


async def test_record_snapshot_and_history_order(source, cache):
    record_snapshot()
    await execute_trade("AAPL", "buy", 10)
    cache.update("AAPL", 200.0)
    record_snapshot()
    values = [h["total_value"] for h in get_history()]
    assert values == [10000.0, 10000.0, 10100.0]
    assert set(get_history()[0]) == {"recorded_at", "total_value"}
