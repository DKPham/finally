"""LLM chat integration for FinAlly (PLAN §10)."""

from .chat import ChatServices, execute_actions, get_history, handle_chat
from .client import MODEL, call_llm, is_mock_mode, mock_response
from .schema import LLMResponse, TradeInstruction, WatchlistChange, parse_llm_response

__all__ = [
    "MODEL",
    "ChatServices",
    "LLMResponse",
    "TradeInstruction",
    "WatchlistChange",
    "call_llm",
    "execute_actions",
    "get_history",
    "handle_chat",
    "is_mock_mode",
    "mock_response",
    "parse_llm_response",
]
