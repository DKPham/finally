"""Database path resolution, initialization and transactions."""

from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
# backend/app/db/connection.py -> parents[3] is the project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "finally.db"

# Set by init_db(); transaction() uses it so callers never pass paths around.
_db_path: str | None = None


def now_iso() -> str:
    """Current UTC time as ISO 8601 with a trailing Z, second precision."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_path(db_path: str | None) -> str:
    if db_path:
        return str(db_path)
    env = os.environ.get("DB_PATH", "").strip()
    if env:
        return env
    return str(DEFAULT_DB_PATH)


def get_db_path() -> str:
    """Path of the active database (set by init_db, else DB_PATH env, else default)."""
    return _db_path if _db_path is not None else _resolve_path(None)


def _connect(path: str) -> sqlite3.Connection:
    # isolation_level=None: we issue BEGIN/COMMIT ourselves.
    conn = sqlite3.connect(path, isolation_level=None, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def init_db(db_path: str | None = None) -> None:
    """Create the DB file and tables if missing, enable WAL, and seed once.

    Safe to call repeatedly. Seeds only when users_profile is empty.

    In-memory databases are rejected: transaction() opens a new connection each
    time, and every new ":memory:" connection is a separate, empty database.
    """
    global _db_path
    path = _resolve_path(db_path)
    if _is_memory_path(path):
        raise ValueError(
            "In-memory SQLite databases are not supported (each transaction opens a new "
            "connection); use a file path, e.g. tmp_path / 'test.db' in tests."
        )
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    from .seed import seed_if_empty

    # Schema and seed run on one connection; the seed is a single transaction.
    conn = _connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA_PATH.read_text())
        conn.execute("BEGIN IMMEDIATE")
        try:
            seeded = seed_if_empty(conn)
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    finally:
        conn.close()

    _db_path = path
    if seeded:
        logger.info("Seeded new database at %s", path)


def _is_memory_path(path: str) -> bool:
    p = path.strip()
    return p == "" or p == ":memory:" or (p.startswith("file:") and "mode=memory" in p) or (
        p.startswith("file::memory:")
    )


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Open a connection and run the block inside BEGIN IMMEDIATE ... COMMIT.

    Rolls back and re-raises on any exception. The connection is closed afterwards.
    """
    conn = _connect(get_db_path())
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")
    finally:
        conn.close()
