"""Chat flow (PLAN §10): persist, build prompt, call LLM, auto-execute, persist, respond."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app import db

from . import client
from .prompt import HISTORY_LIMIT, build_messages, build_portfolio_context
from .schema import LLMResponse, TradeInstruction, WatchlistChange

logger = logging.getLogger(__name__)

NOT_CONFIGURED_MESSAGE = (
    "The AI assistant isn't configured yet — add an OPENROUTER_API_KEY to the .env file "
    "and restart to enable chat. You can still trade manually."
)
ERROR_MESSAGE = "Sorry, I couldn't reach the AI service — please try again."
INVALID_MESSAGE = "Sorry, I got a garbled response from the AI service — please try again."

# Hard ceiling in case the HTTP client ignores its own timeout.
_OUTER_TIMEOUT = client.TIMEOUT_SECONDS + 5


@dataclass
class ChatServices:
    """The app.services functions the chat flow depends on (injectable for tests)."""

    get_portfolio: Callable[[], dict]
    list_watchlist: Callable[[], list[dict]]
    execute_trade: Callable[[str, str, float], Awaitable[dict] | dict]
    add_ticker: Callable[[str], Awaitable[dict] | dict]
    remove_ticker: Callable[[str], Awaitable[None] | None]
    error_type: type[Exception]


def default_services() -> ChatServices:
    from app.services import ServiceError, portfolio, watchlist

    return ChatServices(
        get_portfolio=portfolio.get_portfolio,
        list_watchlist=watchlist.list_watchlist,
        execute_trade=portfolio.execute_trade,
        add_ticker=watchlist.add_ticker,
        remove_ticker=watchlist.remove_ticker,
        error_type=ServiceError,
    )


def _error_detail(exc: Exception) -> str:
    return str(getattr(exc, "detail", None) or exc)


def _display_ticker(raw: str) -> str:
    return raw.strip().upper()


async def _call(fn: Callable, *args: Any) -> Any:
    """Call a service function that may be sync or async."""
    result = fn(*args)
    if inspect.isawaitable(result):
        result = await result
    return result


# --- Action execution -----------------------------------------------------------------


async def _run_trade(svc: ChatServices, t: TradeInstruction) -> dict:
    result: dict[str, Any] = {
        "type": "trade",
        "ticker": _display_ticker(t.ticker),
        "side": t.side,
        "quantity": t.quantity,
        "status": "failed",
        "price": None,
        "error": None,
    }
    if not t.quantity > 0:
        result["error"] = "Quantity must be greater than 0"
        return result
    try:
        out = await _call(svc.execute_trade, t.ticker, t.side, t.quantity)
    except svc.error_type as exc:
        result["error"] = _error_detail(exc)
        return result
    except Exception as exc:  # never let one action break the whole response
        logger.exception("Unexpected error executing LLM trade %s", t)
        result["error"] = f"Unexpected error: {exc}"
        return result
    trade = out.get("trade", {})
    result.update(
        status="executed",
        ticker=trade.get("ticker", result["ticker"]),
        quantity=trade.get("quantity", t.quantity),
        price=trade.get("price"),
    )
    return result


async def _run_watchlist(svc: ChatServices, w: WatchlistChange) -> dict:
    result: dict[str, Any] = {
        "type": "watchlist",
        "ticker": _display_ticker(w.ticker),
        "action": w.action,
        "status": "failed",
        "error": None,
    }
    try:
        if w.action == "add":
            entry = await _call(svc.add_ticker, w.ticker)
            if isinstance(entry, dict) and entry.get("ticker"):
                result["ticker"] = entry["ticker"]
        else:
            await _call(svc.remove_ticker, w.ticker)
    except svc.error_type as exc:
        result["error"] = _error_detail(exc)
        return result
    except Exception as exc:
        logger.exception("Unexpected error applying LLM watchlist change %s", w)
        result["error"] = f"Unexpected error: {exc}"
        return result
    result["status"] = "executed"
    return result


async def execute_actions(svc: ChatServices, response: LLMResponse) -> list[dict]:
    """Run actions sequentially, each against the state left by the previous one.

    Order: watchlist adds, then trades, then watchlist removes — so "watch X and buy X"
    and "sell all X and unwatch X" both behave as the user expects.
    """
    adds = [w for w in response.watchlist_changes if w.action == "add"]
    removes = [w for w in response.watchlist_changes if w.action == "remove"]
    results = [await _run_watchlist(svc, w) for w in adds]
    results += [await _run_trade(svc, t) for t in response.trades]
    results += [await _run_watchlist(svc, w) for w in removes]
    return results


# --- Main flow ------------------------------------------------------------------------


async def _get_llm_response(user_message: str, history: list[dict], svc: ChatServices):
    """Return (LLMResponse | None, fallback_message). None means nothing to execute."""
    if client.is_mock_mode():
        return client.mock_response(user_message), None
    if not client.is_configured():
        logger.warning("Chat requested but OPENROUTER_API_KEY is not set")
        return None, NOT_CONFIGURED_MESSAGE
    try:
        context = build_portfolio_context(svc.get_portfolio(), svc.list_watchlist())
        messages = build_messages(history, context, user_message)
        return await asyncio.wait_for(client.call_llm(messages), _OUTER_TIMEOUT), None
    except ValueError as exc:  # includes pydantic.ValidationError
        logger.error("LLM returned an invalid structured response: %s", exc)
        return None, INVALID_MESSAGE
    except Exception as exc:  # timeouts, network, auth, provider errors
        logger.error("LLM call failed: %s: %s", type(exc).__name__, exc)
        return None, ERROR_MESSAGE


async def handle_chat(user_message: str, svc: ChatServices | None = None) -> dict:
    """Process one user chat message and return {"message", "actions"}."""
    svc = svc or default_services()

    with db.transaction() as conn:
        user_row = db.insert_chat_message(conn, "user", user_message, None)
        recent = db.list_chat_messages(conn, limit=HISTORY_LIMIT + 1)
    history = [m for m in recent if m["id"] != user_row["id"]][-HISTORY_LIMIT:]

    response, fallback = await _get_llm_response(user_message, history, svc)
    if response is None:
        message, actions = fallback, []
    else:
        message = response.message
        actions = await execute_actions(svc, response)

    with db.transaction() as conn:
        db.insert_chat_message(conn, "assistant", message, actions)
    return {"message": message, "actions": actions}


def get_history(limit: int = 50) -> list[dict]:
    with db.transaction() as conn:
        rows = db.list_chat_messages(conn, limit=limit)
    return [
        {
            "id": r["id"],
            "role": r["role"],
            "content": r["content"],
            "actions": r["actions"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
