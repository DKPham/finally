"""Repository functions. Each takes a connection (from transaction()) first.

Rows are returned as plain dicts. Ordering ties on equal timestamps are broken by
SQLite rowid, i.e. insertion order.
"""

from __future__ import annotations

import json
import sqlite3
import uuid

from .connection import now_iso


class DuplicateError(Exception):
    """Row already exists (unique constraint)."""


class NotFoundError(Exception):
    """Requested row does not exist."""


def _new_id() -> str:
    return str(uuid.uuid4())


# --- users_profile -----------------------------------------------------------


def get_cash(conn: sqlite3.Connection, user_id: str = "default") -> float:
    row = conn.execute("SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"User {user_id!r} not found")
    return float(row["cash_balance"])


def set_cash(conn: sqlite3.Connection, amount: float, user_id: str = "default") -> None:
    cur = conn.execute(
        "UPDATE users_profile SET cash_balance = ? WHERE id = ?", (float(amount), user_id)
    )
    if cur.rowcount == 0:
        raise NotFoundError(f"User {user_id!r} not found")


# --- watchlist ---------------------------------------------------------------


def list_watchlist(conn: sqlite3.Connection, user_id: str = "default") -> list[dict]:
    rows = conn.execute(
        "SELECT ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at, rowid",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_watchlist(conn: sqlite3.Connection, ticker: str, user_id: str = "default") -> dict:
    added_at = now_iso()
    try:
        conn.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            (_new_id(), user_id, ticker, added_at),
        )
    except sqlite3.IntegrityError as e:
        raise DuplicateError(f"{ticker} is already on the watchlist") from e
    return {"ticker": ticker, "added_at": added_at}


def remove_watchlist(conn: sqlite3.Connection, ticker: str, user_id: str = "default") -> None:
    cur = conn.execute(
        "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (user_id, ticker)
    )
    if cur.rowcount == 0:
        raise NotFoundError(f"{ticker} is not on the watchlist")


def count_watchlist(conn: sqlite3.Connection, user_id: str = "default") -> int:
    return conn.execute("SELECT COUNT(*) FROM watchlist WHERE user_id = ?", (user_id,)).fetchone()[0]


# --- positions ---------------------------------------------------------------

_POSITION_COLS = "ticker, quantity, avg_cost, updated_at"


def list_positions(conn: sqlite3.Connection, user_id: str = "default") -> list[dict]:
    rows = conn.execute(
        f"SELECT {_POSITION_COLS} FROM positions WHERE user_id = ? ORDER BY ticker",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_position(conn: sqlite3.Connection, ticker: str, user_id: str = "default") -> dict | None:
    row = conn.execute(
        f"SELECT {_POSITION_COLS} FROM positions WHERE user_id = ? AND ticker = ?",
        (user_id, ticker),
    ).fetchone()
    return dict(row) if row else None


def upsert_position(
    conn: sqlite3.Connection,
    ticker: str,
    quantity: float,
    avg_cost: float,
    user_id: str = "default",
) -> None:
    conn.execute(
        """
        INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (user_id, ticker) DO UPDATE SET
            quantity = excluded.quantity,
            avg_cost = excluded.avg_cost,
            updated_at = excluded.updated_at
        """,
        (_new_id(), user_id, ticker, float(quantity), float(avg_cost), now_iso()),
    )


def delete_position(conn: sqlite3.Connection, ticker: str, user_id: str = "default") -> None:
    """Delete a position row. No error if it does not exist."""
    conn.execute("DELETE FROM positions WHERE user_id = ? AND ticker = ?", (user_id, ticker))


# --- trades ------------------------------------------------------------------


def insert_trade(
    conn: sqlite3.Connection,
    ticker: str,
    side: str,
    quantity: float,
    price: float,
    user_id: str = "default",
) -> dict:
    trade = {
        "id": _new_id(),
        "ticker": ticker,
        "side": side,
        "quantity": float(quantity),
        "price": float(price),
        "executed_at": now_iso(),
    }
    conn.execute(
        "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (trade["id"], user_id, ticker, side, trade["quantity"], trade["price"], trade["executed_at"]),
    )
    return trade


def list_trades(conn: sqlite3.Connection, limit: int = 100, user_id: str = "default") -> list[dict]:
    """Most recent `limit` trades, oldest first. (Extra helper, not in the contract.)"""
    rows = conn.execute(
        "SELECT id, ticker, side, quantity, price, executed_at FROM trades WHERE user_id = ? "
        "ORDER BY executed_at DESC, rowid DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


# --- portfolio_snapshots -----------------------------------------------------


def insert_snapshot(conn: sqlite3.Connection, total_value: float, user_id: str = "default") -> None:
    conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, ?, ?, ?)",
        (_new_id(), user_id, float(total_value), now_iso()),
    )


def list_snapshots(
    conn: sqlite3.Connection, limit: int = 1000, user_id: str = "default"
) -> list[dict]:
    """Most recent `limit` snapshots, oldest first: [{recorded_at, total_value}]."""
    rows = conn.execute(
        "SELECT recorded_at, total_value FROM portfolio_snapshots WHERE user_id = ? "
        "ORDER BY recorded_at DESC, rowid DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


# --- chat_messages -----------------------------------------------------------


def insert_chat_message(
    conn: sqlite3.Connection,
    role: str,
    content: str,
    actions: list | None,
    user_id: str = "default",
) -> dict:
    msg = {
        "id": _new_id(),
        "role": role,
        "content": content,
        "actions": actions,
        "created_at": now_iso(),
    }
    conn.execute(
        "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            msg["id"],
            user_id,
            role,
            content,
            json.dumps(actions) if actions is not None else None,
            msg["created_at"],
        ),
    )
    return msg


def list_chat_messages(
    conn: sqlite3.Connection, limit: int = 50, user_id: str = "default"
) -> list[dict]:
    """Most recent `limit` messages, oldest first; `actions` decoded from JSON."""
    rows = conn.execute(
        "SELECT id, role, content, actions, created_at FROM chat_messages WHERE user_id = ? "
        "ORDER BY created_at DESC, rowid DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    out = []
    for r in reversed(rows):
        d = dict(r)
        d["actions"] = json.loads(d["actions"]) if d["actions"] is not None else None
        out.append(d)
    return out
