"""Watchlist service: normalization, cap, and keeping the market source in sync.

The market source tracks watchlist ∪ tickers with open positions (PLAN §6).
"""

from __future__ import annotations

import re

from app import db

from . import state
from .errors import ServiceError

MAX_WATCHLIST = 30
TICKER_RE = re.compile(r"^[A-Z][A-Z.]{0,5}$")


def normalize_ticker(raw: str) -> str:
    """Uppercase and validate a ticker symbol. Raises ServiceError(422) if invalid."""
    if not isinstance(raw, str):
        raise ServiceError(422, f"Invalid ticker: {raw!r}")
    ticker = raw.strip().upper()
    if not TICKER_RE.fullmatch(ticker):
        raise ServiceError(422, f"Invalid ticker: {raw!r} (expected 1-6 letters, e.g. AAPL)")
    return ticker


def _entry(ticker: str, added_at: str) -> dict:
    update = state.price_cache.get(ticker)
    return {
        "ticker": ticker,
        "price": update.price if update else None,
        "previous_price": update.previous_price if update else None,
        "session_change_percent": update.session_change_percent if update else None,
        "added_at": added_at,
    }


def list_watchlist() -> list[dict]:
    """GET /api/watchlist shape, in the order added."""
    with db.transaction() as conn:
        rows = db.list_watchlist(conn)
    return [_entry(r["ticker"], r["added_at"]) for r in rows]


def is_watched(ticker: str) -> bool:
    with db.transaction() as conn:
        return any(r["ticker"] == ticker for r in db.list_watchlist(conn))


def tracked_tickers() -> list[str]:
    """Watchlist ∪ open-position tickers (watchlist order first)."""
    with db.transaction() as conn:
        tickers = [r["ticker"] for r in db.list_watchlist(conn)]
        held = [p["ticker"] for p in db.list_positions(conn)]
    return tickers + [t for t in held if t not in tickers]


async def track(ticker: str) -> None:
    """Make sure the market source is producing prices for ticker."""
    if state.market_source is not None:
        await state.market_source.add_ticker(ticker)


async def untrack_if_unused(ticker: str) -> None:
    """Stop tracking ticker if it is neither watched nor held."""
    with db.transaction() as conn:
        watched = any(r["ticker"] == ticker for r in db.list_watchlist(conn))
        held = db.get_position(conn, ticker) is not None
    if not watched and not held and state.market_source is not None:
        await state.market_source.remove_ticker(ticker)


async def add_ticker(ticker: str) -> dict:
    """Add a ticker to the watchlist and the market source.

    Raises ServiceError 422 (invalid), 409 (duplicate), 400 (watchlist full).
    """
    ticker = normalize_ticker(ticker)
    with db.transaction() as conn:
        if any(r["ticker"] == ticker for r in db.list_watchlist(conn)):
            raise ServiceError(409, f"{ticker} is already on the watchlist")
        if db.count_watchlist(conn) >= MAX_WATCHLIST:
            raise ServiceError(400, f"Watchlist is full (max {MAX_WATCHLIST} tickers)")
        try:
            row = db.add_watchlist(conn, ticker)
        except db.DuplicateError as e:
            raise ServiceError(409, f"{ticker} is already on the watchlist") from e
    await track(ticker)
    return _entry(row["ticker"], row["added_at"])


async def remove_ticker(ticker: str) -> None:
    """Remove a ticker from the watchlist. Raises ServiceError(404) if absent.

    The ticker stays in the market source while a position in it is open.
    """
    ticker = normalize_ticker(ticker)
    with db.transaction() as conn:
        try:
            db.remove_watchlist(conn, ticker)
        except db.NotFoundError as e:
            raise ServiceError(404, f"{ticker} is not on the watchlist") from e
    await untrack_if_unused(ticker)
