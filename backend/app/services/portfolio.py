"""Portfolio service: valuation, trade execution (PLAN §9) and snapshots."""

from __future__ import annotations

import math
import sqlite3

from app import db

from . import state
from . import watchlist as wl
from .errors import ServiceError

QTY_DECIMALS = 4
MIN_QTY = 0.0001
SELL_TOLERANCE = 1e-6


def _money(x: float) -> str:
    return f"${x:,.2f}"


def _qty(x: float) -> str:
    return f"{x:,.4f}".rstrip("0").rstrip(".")


def _portfolio_from_conn(conn: sqlite3.Connection) -> dict:
    cash = db.get_cash(conn)
    positions = []
    positions_value = 0.0
    cost_basis = 0.0
    for p in db.list_positions(conn):
        qty = p["quantity"]
        avg = p["avg_cost"]
        price = state.price_cache.get_price(p["ticker"])
        if price is None:
            price = avg
        mv = qty * price
        pnl = mv - qty * avg
        positions_value += mv
        cost_basis += qty * avg
        positions.append(
            {
                "ticker": p["ticker"],
                "quantity": round(qty, QTY_DECIMALS),
                "avg_cost": round(avg, 4),
                "current_price": round(price, 4),
                "market_value": round(mv, 2),
                "unrealized_pnl": round(pnl, 2),
                "unrealized_pnl_percent": round(pnl / (qty * avg) * 100, 4) if avg else 0.0,
            }
        )
    return {
        "cash_balance": round(cash, 2),
        "positions_value": round(positions_value, 2),
        "total_value": round(cash + positions_value, 2),
        "unrealized_pnl": round(positions_value - cost_basis, 2),
        "positions": positions,
    }


def get_portfolio() -> dict:
    """GET /api/portfolio shape (PLAN §8)."""
    with db.transaction() as conn:
        return _portfolio_from_conn(conn)


def record_snapshot() -> None:
    """Insert one portfolio_snapshots row with the current total value."""
    with db.transaction() as conn:
        db.insert_snapshot(conn, _portfolio_from_conn(conn)["total_value"])


def get_history(limit: int = 1000) -> list[dict]:
    """Most recent snapshots, oldest first."""
    with db.transaction() as conn:
        return db.list_snapshots(conn, limit=limit)


def _validate_quantity(quantity: float) -> float:
    try:
        q = float(quantity)
    except (TypeError, ValueError) as e:
        raise ServiceError(422, f"Invalid quantity: {quantity!r}") from e
    if not math.isfinite(q) or q <= 0:
        raise ServiceError(422, "Quantity must be greater than 0")
    q = round(q, QTY_DECIMALS)
    if q < MIN_QTY:
        raise ServiceError(400, f"Quantity must be at least {MIN_QTY}")
    return q


def _fill(ticker: str, side: str, qty: float) -> tuple[dict, bool]:
    """Validate and apply one trade in a single transaction. Returns (trade, closed)."""
    price = state.price_cache.get_price(ticker)
    if price is None:
        raise ServiceError(400, f"No price available for {ticker} yet")

    closed = False
    with db.transaction() as conn:
        cash = db.get_cash(conn)
        pos = db.get_position(conn, ticker)
        held = pos["quantity"] if pos else 0.0

        if side == "buy":
            cost = qty * price
            if cost > cash + 1e-9:
                raise ServiceError(
                    400, f"Insufficient cash: need {_money(cost)}, have {_money(cash)}"
                )
            new_qty = held + qty
            new_avg = (held * pos["avg_cost"] + cost) / new_qty if pos else price
            db.set_cash(conn, cash - cost)
            db.upsert_position(conn, ticker, round(new_qty, QTY_DECIMALS), new_avg)
        else:
            if qty > held + SELL_TOLERANCE:
                raise ServiceError(
                    400,
                    f"Insufficient shares: you hold {_qty(held)} {ticker}, "
                    f"tried to sell {_qty(qty)}",
                )
            qty = min(qty, held)  # "sell all" within tolerance sells exactly what's held
            db.set_cash(conn, cash + qty * price)
            remaining = held - qty
            if remaining < SELL_TOLERANCE:
                db.delete_position(conn, ticker)
                closed = True
            else:
                db.upsert_position(conn, ticker, round(remaining, QTY_DECIMALS), pos["avg_cost"])

        trade = db.insert_trade(conn, ticker, side, qty, price)
        db.insert_snapshot(conn, _portfolio_from_conn(conn)["total_value"])
    return trade, closed


async def execute_trade(ticker: str, side: str, quantity: float) -> dict:
    """Execute a market order at the cached price. Returns {"trade", "portfolio"}.

    Raises ServiceError (400 business rule, 422 invalid input).
    """
    ticker = wl.normalize_ticker(ticker)
    side = side.lower().strip() if isinstance(side, str) else side
    if side not in ("buy", "sell"):
        raise ServiceError(422, f"Invalid side: {side!r} (expected 'buy' or 'sell')")
    qty = _validate_quantity(quantity)

    # Trading an unwatched ticker adds it to the watchlist (and market source) first.
    if not wl.is_watched(ticker):
        try:
            await wl.add_ticker(ticker)
        except ServiceError as e:
            # 409: added concurrently, fine. 400: watchlist full, so trade anyway and
            # track the ticker via the (soon) open position instead.
            if e.status_code not in (400, 409):
                raise
            await wl.track(ticker)

    try:
        trade, closed = _fill(ticker, side, qty)
    except ServiceError:
        await wl.untrack_if_unused(ticker)  # only matters if the watchlist was full
        raise

    if closed:
        await wl.untrack_if_unused(ticker)

    return {"trade": trade, "portfolio": get_portfolio()}
