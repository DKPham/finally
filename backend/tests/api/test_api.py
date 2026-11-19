"""REST API: status codes and response shapes (PLAN §8)."""

from __future__ import annotations

import pytest

PORTFOLIO_KEYS = {"cash_balance", "positions_value", "total_value", "unrealized_pnl", "positions"}
POSITION_KEYS = {"ticker", "quantity", "avg_cost", "current_price", "market_value",
                 "unrealized_pnl", "unrealized_pnl_percent"}
WATCH_KEYS = {"ticker", "price", "previous_price", "session_change_percent", "added_at"}


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_lifespan_starts_source_and_records_snapshot(client):
    assert client.source.started
    assert len(client.source.get_tickers()) == 10
    history = client.get("/api/portfolio/history").json()
    assert len(history) == 1
    assert history[0]["total_value"] == 10000.0
    assert set(history[0]) == {"recorded_at", "total_value"}


def test_get_portfolio(client):
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == PORTFOLIO_KEYS
    assert body["cash_balance"] == 10000.0
    assert body["positions"] == []


def test_buy_and_sell(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "aapl", "quantity": 10, "side": "buy"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"trade", "portfolio"}
    assert set(body["trade"]) == {"id", "ticker", "side", "quantity", "price", "executed_at"}
    assert body["trade"]["ticker"] == "AAPL"
    assert body["trade"]["price"] == 190.0
    assert body["portfolio"]["cash_balance"] == 8100.0
    assert set(body["portfolio"]["positions"][0]) == POSITION_KEYS

    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "sell"})
    assert r.status_code == 200
    assert r.json()["portfolio"]["positions"] == []
    assert r.json()["portfolio"]["cash_balance"] == 10000.0
    assert len(client.get("/api/portfolio/history").json()) == 3  # startup + 2 trades


def test_insufficient_cash_400(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "NVDA", "quantity": 100, "side": "buy"})
    assert r.status_code == 400
    assert r.json() == {"detail": "Insufficient cash: need $80,000.00, have $10,000.00"}


def test_insufficient_shares_400(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "TSLA", "quantity": 1, "side": "sell"})
    assert r.status_code == 400
    assert "Insufficient shares" in r.json()["detail"]


def test_no_price_400(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "ZZZ", "quantity": 1, "side": "buy"})
    assert r.status_code == 400
    assert r.json()["detail"] == "No price available for ZZZ yet"


@pytest.mark.parametrize("payload", [
    {"ticker": "AAPL", "quantity": 0, "side": "buy"},
    {"ticker": "AAPL", "quantity": -1, "side": "buy"},
    {"ticker": "AAPL", "quantity": 1, "side": "hold"},
    {"ticker": "AAPL", "side": "buy"},
    {"ticker": "123", "quantity": 1, "side": "buy"},
    {"quantity": 1, "side": "buy"},
])
def test_trade_validation_422(client, payload):
    r = client.post("/api/portfolio/trade", json=payload)
    assert r.status_code == 422
    assert "detail" in r.json()


def test_get_watchlist(client):
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 10
    assert items[0]["ticker"] == "AAPL"
    assert set(items[0]) == WATCH_KEYS


def test_add_and_remove_watchlist(client):
    r = client.post("/api/watchlist", json={"ticker": "pypl"})
    assert r.status_code == 201
    assert r.json()["ticker"] == "PYPL"
    assert set(r.json()) == WATCH_KEYS
    assert client.get("/api/watchlist").json()[-1]["ticker"] == "PYPL"

    r = client.delete("/api/watchlist/pypl")
    assert r.status_code == 204
    assert r.content == b""
    assert "PYPL" not in [i["ticker"] for i in client.get("/api/watchlist").json()]


def test_add_duplicate_409(client):
    r = client.post("/api/watchlist", json={"ticker": "AAPL"})
    assert r.status_code == 409
    assert r.json() == {"detail": "AAPL is already on the watchlist"}


def test_add_invalid_422(client):
    assert client.post("/api/watchlist", json={"ticker": "not a ticker"}).status_code == 422
    assert client.post("/api/watchlist", json={}).status_code == 422


def test_watchlist_full_400(client):
    for i in range(20):
        assert client.post("/api/watchlist", json={"ticker": "Q" + "ABCDEFGHIJKLMNOPQRST"[i]}).status_code == 201
    r = client.post("/api/watchlist", json={"ticker": "PYPL"})
    assert r.status_code == 400


def test_remove_missing_404(client):
    r = client.delete("/api/watchlist/PYPL")
    assert r.status_code == 404
    assert r.json() == {"detail": "PYPL is not on the watchlist"}


def test_remove_held_ticker_keeps_source(client):
    client.post("/api/portfolio/trade", json={"ticker": "TSLA", "quantity": 1, "side": "buy"})
    assert client.delete("/api/watchlist/TSLA").status_code == 204
    assert "TSLA" in client.source.get_tickers()
    pos = client.get("/api/portfolio").json()["positions"][0]
    assert pos["current_price"] == 250.0


def test_sse_stream_route_registered(client):
    paths = {r.path for r in client.app.routes}
    assert "/api/stream/prices" in paths
    assert "/api/chat" in paths
    assert "/api/chat/history" in paths
