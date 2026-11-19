"""Fixtures for LLM/chat tests: a temp DB and in-memory fake services."""

from __future__ import annotations

import os

# Before any test module imports litellm: no network fetch of the model cost map.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import pytest  # noqa: E402

from app import db
from app.llm.chat import ChatServices


class FakeServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class FakeBroker:
    """Minimal stand-in for app.services with fixed prices."""

    def __init__(self):
        self.cash = 10000.0
        self.prices = {"AAPL": 190.0, "NVDA": 900.0, "TSLA": 250.0}
        self.positions: dict[str, float] = {}
        self.watch = ["AAPL", "NVDA"]
        self.calls: list[tuple] = []

    def get_portfolio(self):
        positions = [
            {
                "ticker": t,
                "quantity": q,
                "avg_cost": self.prices[t],
                "current_price": self.prices[t],
                "market_value": q * self.prices[t],
                "unrealized_pnl": 0.0,
                "unrealized_pnl_percent": 0.0,
            }
            for t, q in self.positions.items()
        ]
        pv = sum(p["market_value"] for p in positions)
        return {
            "cash_balance": self.cash,
            "positions_value": pv,
            "total_value": self.cash + pv,
            "unrealized_pnl": 0.0,
            "positions": positions,
        }

    def list_watchlist(self):
        return [
            {"ticker": t, "price": self.prices.get(t), "previous_price": None,
             "session_change_percent": 0.1, "added_at": "2026-11-16T14:00:00Z"}
            for t in self.watch
        ]

    async def execute_trade(self, ticker, side, quantity):
        ticker = ticker.upper()
        self.calls.append(("trade", ticker, side, quantity))
        if ticker not in self.watch:
            self.watch.append(ticker)
        price = self.prices.get(ticker)
        if price is None:
            raise FakeServiceError(400, f"No price available for {ticker} yet")
        held = self.positions.get(ticker, 0.0)
        if side == "buy":
            if quantity * price > self.cash:
                raise FakeServiceError(400, "Insufficient cash")
            self.cash -= quantity * price
            self.positions[ticker] = held + quantity
        else:
            if quantity > held + 1e-6:
                raise FakeServiceError(400, f"Insufficient shares: you hold {held:g}")
            self.cash += quantity * price
            if held - quantity < 1e-6:
                self.positions.pop(ticker, None)
            else:
                self.positions[ticker] = held - quantity
        return {
            "trade": {"id": "x", "ticker": ticker, "side": side, "quantity": quantity,
                      "price": price, "executed_at": "2026-11-16T14:03:22Z"},
            "portfolio": self.get_portfolio(),
        }

    async def add_ticker(self, ticker):
        ticker = ticker.upper()
        self.calls.append(("add", ticker))
        if ticker in self.watch:
            raise FakeServiceError(409, f"{ticker} is already on the watchlist")
        self.watch.append(ticker)
        return {"ticker": ticker}

    async def remove_ticker(self, ticker):
        ticker = ticker.upper()
        self.calls.append(("remove", ticker))
        if ticker not in self.watch:
            raise FakeServiceError(404, f"{ticker} is not on the watchlist")
        self.watch.remove(ticker)

    def services(self) -> ChatServices:
        return ChatServices(
            get_portfolio=self.get_portfolio,
            list_watchlist=self.list_watchlist,
            execute_trade=self.execute_trade,
            add_ticker=self.add_ticker,
            remove_ticker=self.remove_ticker,
            error_type=FakeServiceError,
        )


@pytest.fixture
def temp_db(tmp_path):
    db.init_db(str(tmp_path / "test.db"))


@pytest.fixture
def broker():
    return FakeBroker()


@pytest.fixture
def no_mock(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "false")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
