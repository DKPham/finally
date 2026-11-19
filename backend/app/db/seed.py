"""Default seed data: one user with $10,000 and ten watchlist tickers."""

from __future__ import annotations

import sqlite3
import uuid

from .connection import now_iso

DEFAULT_USER_ID = "default"
DEFAULT_CASH = 10000.0
DEFAULT_WATCHLIST = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]


def seed_if_empty(conn: sqlite3.Connection) -> bool:
    """Seed default data if users_profile has no rows. Returns True if it seeded."""
    if conn.execute("SELECT 1 FROM users_profile LIMIT 1").fetchone() is not None:
        return False
    ts = now_iso()
    conn.execute(
        "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
        (DEFAULT_USER_ID, DEFAULT_CASH, ts),
    )
    conn.executemany(
        "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        [(str(uuid.uuid4()), DEFAULT_USER_ID, t, ts) for t in DEFAULT_WATCHLIST],
    )
    return True
