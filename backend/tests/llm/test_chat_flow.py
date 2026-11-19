"""End-to-end chat flow with a temp DB, fake services and a monkeypatched LLM call."""

import asyncio

import litellm
import pytest

from app import db
from app.llm import chat as chat_mod
from app.llm import client
from app.llm.chat import ERROR_MESSAGE, INVALID_MESSAGE, NOT_CONFIGURED_MESSAGE, handle_chat
from app.llm.schema import LLMResponse, TradeInstruction, WatchlistChange

pytestmark = pytest.mark.usefixtures("temp_db")


def _patch_llm(monkeypatch, result=None, exc=None, capture=None):
    async def fake_call(messages):
        if capture is not None:
            capture.append(messages)
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr(client, "call_llm", fake_call)


def _messages():
    with db.transaction() as conn:
        return db.list_chat_messages(conn)


async def test_mock_mode_buy(monkeypatch, broker):
    monkeypatch.setenv("LLM_MOCK", "true")
    out = await handle_chat("buy 1 AAPL", broker.services())
    assert out == {
        "message": "Buying 1 AAPL.",
        "actions": [{"type": "trade", "ticker": "AAPL", "side": "buy", "quantity": 1.0,
                     "status": "executed", "price": 190.0, "error": None}],
    }
    assert broker.positions == {"AAPL": 1.0}
    msgs = _messages()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["actions"] is None
    assert msgs[1]["actions"] == out["actions"]


async def test_mock_mode_works_without_key(monkeypatch, broker):
    monkeypatch.setenv("LLM_MOCK", "true")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    out = await handle_chat("watch PYPL", broker.services())
    assert out["actions"] == [{"type": "watchlist", "ticker": "PYPL", "action": "add",
                               "status": "executed", "error": None}]


async def test_trades_execute_sequentially_and_failures_recorded(monkeypatch, broker, no_mock):
    _patch_llm(monkeypatch, LLMResponse(
        message="Doing it",
        trades=[
            TradeInstruction(ticker="nvda", side="buy", quantity=5),
            TradeInstruction(ticker="NVDA", side="buy", quantity=10),  # cash now insufficient
            TradeInstruction(ticker="TSLA", side="sell", quantity=1),  # none held
            TradeInstruction(ticker="NVDA", side="sell", quantity=5),
        ],
        watchlist_changes=[WatchlistChange(ticker="AAPL", action="add")],
    ))
    out = await handle_chat("go", broker.services())
    a = out["actions"]
    assert a[0] == {"type": "watchlist", "ticker": "AAPL", "action": "add", "status": "failed",
                    "error": "AAPL is already on the watchlist"}
    assert a[1]["status"] == "executed" and a[1]["ticker"] == "NVDA" and a[1]["price"] == 900.0
    assert a[2] == {"type": "trade", "ticker": "NVDA", "side": "buy", "quantity": 10.0,
                    "status": "failed", "price": None, "error": "Insufficient cash"}
    assert a[3]["status"] == "failed" and "you hold 0" in a[3]["error"]
    assert a[4]["status"] == "executed"
    assert broker.positions == {}
    assert broker.cash == pytest.approx(10000.0)


async def test_watch_add_runs_before_trade_and_remove_after(monkeypatch, broker, no_mock):
    _patch_llm(monkeypatch, LLMResponse(
        message="m",
        trades=[TradeInstruction(ticker="TSLA", side="buy", quantity=1)],
        watchlist_changes=[WatchlistChange(ticker="NVDA", action="remove"),
                           WatchlistChange(ticker="TSLA", action="add")],
    ))
    out = await handle_chat("go", broker.services())
    assert broker.calls == [("add", "TSLA"), ("trade", "TSLA", "buy", 1.0), ("remove", "NVDA")]
    assert all(x["status"] == "executed" for x in out["actions"])


async def test_non_positive_quantity_fails_without_calling_service(monkeypatch, broker, no_mock):
    _patch_llm(monkeypatch, LLMResponse(
        message="m", trades=[TradeInstruction(ticker="AAPL", side="buy", quantity=0)],
        watchlist_changes=[],
    ))
    out = await handle_chat("go", broker.services())
    assert out["actions"][0]["status"] == "failed"
    assert broker.calls == []


async def test_unexpected_service_exception_is_contained(monkeypatch, broker, no_mock):
    def boom(*a):
        raise RuntimeError("kaboom")

    broker.add_ticker = boom
    _patch_llm(monkeypatch, LLMResponse(
        message="m", trades=[], watchlist_changes=[WatchlistChange(ticker="X", action="add")],
    ))
    out = await handle_chat("go", broker.services())
    assert out["actions"][0]["status"] == "failed"
    assert "kaboom" in out["actions"][0]["error"]


@pytest.mark.parametrize(
    "exc,expected",
    [
        (litellm.Timeout("t", model="m", llm_provider="openrouter"), ERROR_MESSAGE),
        (asyncio.TimeoutError(), ERROR_MESSAGE),
        (RuntimeError("network down"), ERROR_MESSAGE),
        (ValueError("LLM response is not valid JSON"), INVALID_MESSAGE),
    ],
)
async def test_llm_failures_return_friendly_message(monkeypatch, broker, no_mock, exc, expected):
    _patch_llm(monkeypatch, exc=exc)
    out = await handle_chat("hello", broker.services())
    assert out == {"message": expected, "actions": []}
    assert broker.calls == []
    msgs = _messages()
    assert msgs[-1]["role"] == "assistant" and msgs[-1]["content"] == expected
    assert msgs[-1]["actions"] == []


async def test_invalid_json_from_model_returns_friendly_message(monkeypatch, broker, no_mock):
    class Msg:
        content = '{"message": "x", "trades": [{"ticker": "A", "side": "hodl", "quantity": 1}]}'

    class Choice:
        message = Msg()

    class Resp:
        choices = [Choice()]

    async def fake_acompletion(**kwargs):
        assert kwargs["timeout"] == 30.0
        assert kwargs["response_format"] is LLMResponse
        assert kwargs["extra_body"] == {"provider": {"order": ["cerebras"]}}
        return Resp()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    out = await handle_chat("hello", broker.services())
    assert out == {"message": INVALID_MESSAGE, "actions": []}


async def test_missing_key(monkeypatch, broker):
    monkeypatch.setenv("LLM_MOCK", "false")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    _patch_llm(monkeypatch, exc=AssertionError("should not be called"))
    out = await handle_chat("hello", broker.services())
    assert out == {"message": NOT_CONFIGURED_MESSAGE, "actions": []}


async def test_history_passed_to_llm_excludes_new_message_and_includes_results(
    monkeypatch, broker, no_mock
):
    captured = []
    _patch_llm(monkeypatch, LLMResponse(message="ok", trades=[], watchlist_changes=[]),
               capture=captured)
    with db.transaction() as conn:
        db.insert_chat_message(conn, "user", "sell 100 TSLA", None)
        db.insert_chat_message(conn, "assistant", "Selling 100 TSLA.",
                               [{"type": "trade", "status": "failed", "error": "you hold 0"}])
    await handle_chat("what happened?", broker.services())
    msgs = captured[0]
    assert msgs[0]["role"] == "system"
    assert msgs[1] == {"role": "user", "content": "sell 100 TSLA"}
    assert "you hold 0" in msgs[2]["content"]
    assert msgs[-1] == {"role": "user", "content": "what happened?"}
    assert sum(1 for m in msgs if m["content"] == "what happened?") == 1
    assert "Cash: $10,000.00" in msgs[-2]["content"]


async def test_get_history_shape(monkeypatch, broker):
    monkeypatch.setenv("LLM_MOCK", "true")
    await handle_chat("hi", broker.services())
    hist = chat_mod.get_history()
    assert [h["role"] for h in hist] == ["user", "assistant"]
    assert set(hist[0]) == {"id", "role", "content", "actions", "created_at"}
    assert hist[1]["actions"] == []
