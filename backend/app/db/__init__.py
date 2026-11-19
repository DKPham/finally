"""SQLite persistence layer for FinAlly.

Usage:
    from app import db
    db.init_db()                       # at startup
    with db.transaction() as conn:
        cash = db.get_cash(conn)
"""

from .connection import DEFAULT_DB_PATH, get_db_path, init_db, now_iso, transaction
from .repository import (
    DuplicateError,
    NotFoundError,
    add_watchlist,
    count_watchlist,
    delete_position,
    get_cash,
    get_position,
    insert_chat_message,
    insert_snapshot,
    insert_trade,
    list_chat_messages,
    list_positions,
    list_snapshots,
    list_trades,
    list_watchlist,
    remove_watchlist,
    set_cash,
    upsert_position,
)
from .seed import DEFAULT_CASH, DEFAULT_USER_ID, DEFAULT_WATCHLIST

__all__ = [
    "DEFAULT_CASH",
    "DEFAULT_DB_PATH",
    "DEFAULT_USER_ID",
    "DEFAULT_WATCHLIST",
    "DuplicateError",
    "NotFoundError",
    "add_watchlist",
    "count_watchlist",
    "delete_position",
    "get_cash",
    "get_db_path",
    "get_position",
    "init_db",
    "insert_chat_message",
    "insert_snapshot",
    "insert_trade",
    "list_chat_messages",
    "list_positions",
    "list_snapshots",
    "list_trades",
    "list_watchlist",
    "now_iso",
    "remove_watchlist",
    "set_cash",
    "transaction",
    "upsert_position",
]
