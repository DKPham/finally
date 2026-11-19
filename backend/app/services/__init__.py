"""Business logic shared by the REST API and the LLM chat flow."""

from . import state
from .errors import ServiceError
from .portfolio import execute_trade, get_history, get_portfolio, record_snapshot
from .watchlist import (
    MAX_WATCHLIST,
    add_ticker,
    list_watchlist,
    normalize_ticker,
    remove_ticker,
    tracked_tickers,
)

__all__ = [
    "MAX_WATCHLIST",
    "ServiceError",
    "add_ticker",
    "execute_trade",
    "get_history",
    "get_portfolio",
    "list_watchlist",
    "normalize_ticker",
    "record_snapshot",
    "remove_ticker",
    "state",
    "tracked_tickers",
]
