"""LLM calls: LiteLLM -> OpenRouter -> gpt-oss-120b on Cerebras, plus mock mode."""

from __future__ import annotations

import os
import re

from .schema import LLMResponse, TradeInstruction, WatchlistChange, parse_llm_response

# Must be set before litellm is first imported: stops it fetching the model cost map
# from raw.githubusercontent.com (blocked in sandboxes, slow when offline).
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}
TIMEOUT_SECONDS = 30.0


class LLMNotConfiguredError(RuntimeError):
    """OPENROUTER_API_KEY is missing and mock mode is off."""


def is_mock_mode() -> bool:
    return os.environ.get("LLM_MOCK", "").strip().lower() == "true"


def is_configured() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY", "").strip())


# --- Mock mode (PLAN §10) -------------------------------------------------------------

_QTY = r"(\d+(?:\.\d+)?)"
_TICKER = r"([A-Za-z][A-Za-z.]{0,5})"
_BUY = re.compile(rf"\bbuy\s+{_QTY}\s+{_TICKER}\b", re.IGNORECASE)
_SELL = re.compile(rf"\bsell\s+{_QTY}\s+{_TICKER}\b", re.IGNORECASE)
_UNWATCH = re.compile(rf"\bunwatch\s+{_TICKER}\b", re.IGNORECASE)
_WATCH = re.compile(rf"\bwatch\s+{_TICKER}\b", re.IGNORECASE)


def mock_response(user_message: str) -> LLMResponse:
    """Deterministic response from simple pattern matching on the user message."""
    if m := _BUY.search(user_message):
        qty, ticker = m.group(1), m.group(2).upper()
        return LLMResponse(
            message=f"Buying {qty} {ticker}.",
            trades=[TradeInstruction(ticker=ticker, side="buy", quantity=float(qty))],
            watchlist_changes=[],
        )
    if m := _SELL.search(user_message):
        qty, ticker = m.group(1), m.group(2).upper()
        return LLMResponse(
            message=f"Selling {qty} {ticker}.",
            trades=[TradeInstruction(ticker=ticker, side="sell", quantity=float(qty))],
            watchlist_changes=[],
        )
    if m := _UNWATCH.search(user_message):
        ticker = m.group(1).upper()
        return LLMResponse(
            message=f"Removing {ticker} from your watchlist.",
            trades=[],
            watchlist_changes=[WatchlistChange(ticker=ticker, action="remove")],
        )
    if m := _WATCH.search(user_message):
        ticker = m.group(1).upper()
        return LLMResponse(
            message=f"Adding {ticker} to your watchlist.",
            trades=[],
            watchlist_changes=[WatchlistChange(ticker=ticker, action="add")],
        )
    return LLMResponse(message="This is a mock response from FinAlly.", trades=[], watchlist_changes=[])


# --- Real call ------------------------------------------------------------------------


async def call_llm(messages: list[dict]) -> LLMResponse:
    """Call the model with structured output and return the validated response.

    Raises LLMNotConfiguredError, litellm exceptions (incl. timeout) or ValueError
    (invalid/malformed JSON). The caller turns all of these into a friendly message.
    """
    if not is_configured():
        raise LLMNotConfiguredError("OPENROUTER_API_KEY is not set")

    from litellm import acompletion

    response = await acompletion(
        model=MODEL,
        messages=messages,
        response_format=LLMResponse,
        reasoning_effort="low",
        extra_body=EXTRA_BODY,
        timeout=TIMEOUT_SECONDS,
    )
    return parse_llm_response(response.choices[0].message.content)
