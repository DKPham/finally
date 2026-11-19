"""Structured-output schema for the LLM (PLAN §10).

The same Pydantic model is passed to LiteLLM as `response_format` and used to
validate the returned JSON.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TradeInstruction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(description="Ticker symbol, e.g. AAPL")
    side: Literal["buy", "sell"]
    quantity: float = Field(description="Number of shares, must be > 0 (fractional allowed)")


class WatchlistChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(description="Ticker symbol, e.g. PYPL")
    action: Literal["add", "remove"]


class LLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(description="Conversational response shown to the user")
    trades: list[TradeInstruction] = Field(
        description="Trades to execute now; empty list if none"
    )
    watchlist_changes: list[WatchlistChange] = Field(
        description="Watchlist changes to apply now; empty list if none"
    )


def parse_llm_response(raw: str | None) -> LLMResponse:
    """Validate the model's JSON text. Raises ValueError on empty or invalid content.

    Missing `trades` / `watchlist_changes` keys are tolerated and treated as empty.
    """
    if not raw or not raw.strip():
        raise ValueError("empty LLM response")
    text = raw.strip()
    # Some models wrap JSON in a markdown fence despite structured output.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("LLM response is not a JSON object")
    data.setdefault("trades", [])
    data.setdefault("watchlist_changes", [])
    if data["trades"] is None:
        data["trades"] = []
    if data["watchlist_changes"] is None:
        data["watchlist_changes"] = []
    return LLMResponse.model_validate(data)
