"""Unit tests for the app.db persistence layer."""

import re
import sqlite3

import pytest

from app import db
from app.db import connection


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    monkeypatch.delenv("DB_PATH", raising=False)
    path = str(tmp_path / "test.db")
    db.init_db(path)
    yield path
    monkeypatch.setattr(connection, "_db_path", None)


# --- path resolution & init --------------------------------------------------


class TestInit:
    def test_creates_parent_dir_and_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(connection, "_db_path", None)
        path = tmp_path / "nested" / "deeper" / "finally.db"
        db.init_db(str(path))
        assert path.exists()
        assert db.get_db_path() == str(path)

    def test_db_path_env(self, tmp_path, monkeypatch):
        monkeypatch.setattr(connection, "_db_path", None)
        path = tmp_path / "env.db"
        monkeypatch.setenv("DB_PATH", str(path))
        assert db.get_db_path() == str(path)
        db.init_db()
        assert path.exists()

    def test_default_path_is_project_root_db(self, monkeypatch):
        monkeypatch.setattr(connection, "_db_path", None)
        monkeypatch.delenv("DB_PATH", raising=False)
        p = db.get_db_path()
        assert p.endswith("/db/finally.db")
        assert not p.endswith("/backend/db/finally.db")
        assert (connection.PROJECT_ROOT / "backend").is_dir()

    def test_empty_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setattr(connection, "_db_path", None)
        monkeypatch.setenv("DB_PATH", "  ")
        assert db.get_db_path() == str(db.DEFAULT_DB_PATH)

    @pytest.mark.parametrize("path", [":memory:", "file::memory:?cache=shared", "file:x?mode=memory"])
    def test_memory_db_rejected(self, path, tmp_path, monkeypatch):
        good = str(tmp_path / "good.db")
        db.init_db(good)
        with pytest.raises(ValueError, match="In-memory"):
            db.init_db(path)
        # A rejected call leaves the previously configured path untouched.
        assert db.get_db_path() == good
        monkeypatch.setattr(connection, "_db_path", None)

    def test_memory_db_rejected_via_env(self, tmp_path, monkeypatch):
        monkeypatch.setattr(connection, "_db_path", None)
        monkeypatch.setenv("DB_PATH", ":memory:")
        with pytest.raises(ValueError):
            db.init_db()

    def test_fresh_init_seeds_in_single_step(self, tmp_path, monkeypatch):
        monkeypatch.setattr(connection, "_db_path", None)
        path = str(tmp_path / "fresh.db")
        db.init_db(path)
        assert db_count(path, "users_profile") == 1
        assert db_count(path, "watchlist") == 10

    def test_all_tables_exist(self, db_path):
        conn = sqlite3.connect(db_path)
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        assert {
            "users_profile",
            "watchlist",
            "positions",
            "trades",
            "portfolio_snapshots",
            "chat_messages",
        } <= names

    def test_user_id_column_everywhere_but_profile(self, db_path):
        conn = sqlite3.connect(db_path)
        for table in ["watchlist", "positions", "trades", "portfolio_snapshots", "chat_messages"]:
            cols = {r[1]: r for r in conn.execute(f"PRAGMA table_info({table})")}
            assert "user_id" in cols
            assert cols["user_id"][4] == "'default'"
        conn.close()

    def test_wal_mode(self, db_path):
        conn = sqlite3.connect(db_path)
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        conn.close()

    def test_init_idempotent(self, db_path):
        db.init_db(db_path)
        db.init_db(db_path)
        with db.transaction() as conn:
            assert db.count_watchlist(conn) == 10
            assert conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0] == 1

    def test_init_preserves_existing_data(self, db_path):
        with db.transaction() as conn:
            db.set_cash(conn, 1234.5)
            db.remove_watchlist(conn, "AAPL")
            db.upsert_position(conn, "MSFT", 3, 400)
        db.init_db(db_path)
        with db.transaction() as conn:
            assert db.get_cash(conn) == 1234.5
            assert db.count_watchlist(conn) == 9
            assert db.get_position(conn, "MSFT")["quantity"] == 3

    def test_seed_once_even_if_watchlist_emptied(self, db_path):
        with db.transaction() as conn:
            for item in db.list_watchlist(conn):
                db.remove_watchlist(conn, item["ticker"])
        db.init_db(db_path)
        with db.transaction() as conn:
            assert db.count_watchlist(conn) == 0

    def test_reseeds_when_profile_empty(self, db_path):
        with db.transaction() as conn:
            conn.execute("DELETE FROM users_profile")
        db.init_db(db_path)
        with db.transaction() as conn:
            assert db.get_cash(conn) == 10000.0
            assert db.count_watchlist(conn) == 10  # INSERT OR IGNORE: no duplicates


# --- seed --------------------------------------------------------------------


class TestSeed:
    def test_default_cash(self, db_path):
        with db.transaction() as conn:
            assert db.get_cash(conn) == 10000.0

    def test_default_watchlist_in_order(self, db_path):
        with db.transaction() as conn:
            tickers = [w["ticker"] for w in db.list_watchlist(conn)]
        assert tickers == ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]

    def test_profile_row(self, db_path):
        with db.transaction() as conn:
            row = conn.execute("SELECT * FROM users_profile").fetchone()
        assert row["id"] == "default"
        assert row["created_at"].endswith("Z")


# --- now_iso -----------------------------------------------------------------


def test_now_iso_format():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", db.now_iso())


# --- transaction -------------------------------------------------------------


class TestTransaction:
    def test_commit(self, db_path):
        with db.transaction() as conn:
            db.set_cash(conn, 50.0)
        with db.transaction() as conn:
            assert db.get_cash(conn) == 50.0

    def test_rollback_on_exception(self, db_path):
        with pytest.raises(RuntimeError):
            with db.transaction() as conn:
                db.set_cash(conn, 1.0)
                db.upsert_position(conn, "AAPL", 10, 190)
                db.insert_trade(conn, "AAPL", "buy", 10, 190)
                db.insert_snapshot(conn, 1901.0)
                raise RuntimeError("boom")
        with db.transaction() as conn:
            assert db.get_cash(conn) == 10000.0
            assert db.get_position(conn, "AAPL") is None
            assert db.list_trades(conn) == []
            assert db.list_snapshots(conn) == []

    def test_rollback_on_db_error(self, db_path):
        with pytest.raises(db.DuplicateError):
            with db.transaction() as conn:
                db.set_cash(conn, 1.0)
                db.add_watchlist(conn, "AAPL")
        with db.transaction() as conn:
            assert db.get_cash(conn) == 10000.0

    def test_row_factory(self, db_path):
        with db.transaction() as conn:
            row = conn.execute("SELECT id FROM users_profile").fetchone()
            assert isinstance(row, sqlite3.Row)

    def test_connection_closed_after(self, db_path):
        with db.transaction() as conn:
            pass
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_writes_visible_to_other_connection_only_after_commit(self, db_path):
        with db.transaction() as conn:
            db.set_cash(conn, 7.0)
            other = sqlite3.connect(db_path)
            assert other.execute("SELECT cash_balance FROM users_profile").fetchone()[0] == 10000.0
        assert other.execute("SELECT cash_balance FROM users_profile").fetchone()[0] == 7.0
        other.close()


# --- cash --------------------------------------------------------------------


class TestCash:
    def test_set_and_get(self, db_path):
        with db.transaction() as conn:
            db.set_cash(conn, 8094.8)
            assert db.get_cash(conn) == pytest.approx(8094.8)

    def test_unknown_user(self, db_path):
        with db.transaction() as conn:
            with pytest.raises(db.NotFoundError):
                db.get_cash(conn, user_id="nobody")
            with pytest.raises(db.NotFoundError):
                db.set_cash(conn, 1.0, user_id="nobody")


# --- watchlist ---------------------------------------------------------------


class TestWatchlist:
    def test_add_returns_entry(self, db_path):
        with db.transaction() as conn:
            entry = db.add_watchlist(conn, "PYPL")
        assert entry["ticker"] == "PYPL"
        assert entry["added_at"].endswith("Z")

    def test_add_appends_in_order(self, db_path):
        with db.transaction() as conn:
            db.add_watchlist(conn, "PYPL")
            db.add_watchlist(conn, "AMD")
            db.add_watchlist(conn, "BRK.B")
            tickers = [w["ticker"] for w in db.list_watchlist(conn)]
        assert tickers[-3:] == ["PYPL", "AMD", "BRK.B"]
        assert db_count(db_path, "watchlist") == 13

    def test_readd_after_remove_goes_to_end(self, db_path):
        with db.transaction() as conn:
            db.remove_watchlist(conn, "AAPL")
            db.add_watchlist(conn, "AAPL")
            tickers = [w["ticker"] for w in db.list_watchlist(conn)]
        assert tickers[-1] == "AAPL"
        assert tickers.count("AAPL") == 1

    def test_duplicate_raises(self, db_path):
        with db.transaction() as conn:
            with pytest.raises(db.DuplicateError, match="AAPL"):
                db.add_watchlist(conn, "AAPL")

    def test_same_ticker_different_users(self, db_path):
        with db.transaction() as conn:
            db.add_watchlist(conn, "AAPL", user_id="other")
            assert db.count_watchlist(conn, user_id="other") == 1
            assert db.count_watchlist(conn) == 10

    def test_remove(self, db_path):
        with db.transaction() as conn:
            db.remove_watchlist(conn, "TSLA")
            assert "TSLA" not in [w["ticker"] for w in db.list_watchlist(conn)]
            assert db.count_watchlist(conn) == 9

    def test_remove_missing_raises(self, db_path):
        with db.transaction() as conn:
            with pytest.raises(db.NotFoundError):
                db.remove_watchlist(conn, "ZZZZ")

    def test_list_shape(self, db_path):
        with db.transaction() as conn:
            assert set(db.list_watchlist(conn)[0]) == {"ticker", "added_at"}


def db_count(path, table):
    conn = sqlite3.connect(path)
    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.close()
    return n


# --- positions ---------------------------------------------------------------


class TestPositions:
    def test_empty(self, db_path):
        with db.transaction() as conn:
            assert db.list_positions(conn) == []
            assert db.get_position(conn, "AAPL") is None

    def test_insert_and_get(self, db_path):
        with db.transaction() as conn:
            db.upsert_position(conn, "AAPL", 10, 190.52)
            pos = db.get_position(conn, "AAPL")
        assert pos["ticker"] == "AAPL"
        assert pos["quantity"] == 10
        assert pos["avg_cost"] == pytest.approx(190.52)
        assert pos["updated_at"].endswith("Z")
        assert set(pos) == {"ticker", "quantity", "avg_cost", "updated_at"}

    def test_upsert_updates_single_row(self, db_path):
        with db.transaction() as conn:
            db.upsert_position(conn, "AAPL", 10, 190)
            db.upsert_position(conn, "AAPL", 15, 192.5)
            pos = db.get_position(conn, "AAPL")
            assert len(db.list_positions(conn)) == 1
        assert pos["quantity"] == 15
        assert pos["avg_cost"] == 192.5

    def test_fractional_quantity(self, db_path):
        with db.transaction() as conn:
            db.upsert_position(conn, "NVDA", 0.0001, 890.1)
            assert db.get_position(conn, "NVDA")["quantity"] == pytest.approx(0.0001)

    def test_unique_constraint_direct_insert(self, db_path):
        with db.transaction() as conn:
            db.upsert_position(conn, "AAPL", 1, 1)
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
                    "VALUES ('x', 'default', 'AAPL', 1, 1, 'now')"
                )

    def test_list_sorted_by_ticker(self, db_path):
        with db.transaction() as conn:
            for t in ["TSLA", "AAPL", "MSFT"]:
                db.upsert_position(conn, t, 1, 100)
            assert [p["ticker"] for p in db.list_positions(conn)] == ["AAPL", "MSFT", "TSLA"]

    def test_delete(self, db_path):
        with db.transaction() as conn:
            db.upsert_position(conn, "AAPL", 1, 1)
            db.delete_position(conn, "AAPL")
            assert db.get_position(conn, "AAPL") is None

    def test_delete_missing_is_noop(self, db_path):
        with db.transaction() as conn:
            db.delete_position(conn, "ZZZZ")

    def test_user_isolation(self, db_path):
        with db.transaction() as conn:
            db.upsert_position(conn, "AAPL", 5, 100, user_id="other")
            assert db.get_position(conn, "AAPL") is None
            assert db.get_position(conn, "AAPL", user_id="other")["quantity"] == 5


# --- trades ------------------------------------------------------------------


class TestTrades:
    def test_insert_returns_row(self, db_path):
        with db.transaction() as conn:
            trade = db.insert_trade(conn, "AAPL", "buy", 10, 190.52)
        assert set(trade) == {"id", "ticker", "side", "quantity", "price", "executed_at"}
        assert trade["ticker"] == "AAPL"
        assert trade["side"] == "buy"
        assert trade["quantity"] == 10.0
        assert trade["price"] == 190.52
        assert re.fullmatch(r"[0-9a-f-]{36}", trade["id"])
        assert trade["executed_at"].endswith("Z")

    def test_persisted(self, db_path):
        with db.transaction() as conn:
            trade = db.insert_trade(conn, "AAPL", "sell", 2.5, 200)
        with db.transaction() as conn:
            assert db.list_trades(conn) == [trade]

    def test_invalid_side_rejected(self, db_path):
        with db.transaction() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                db.insert_trade(conn, "AAPL", "short", 1, 1)

    def test_list_order_and_limit(self, db_path):
        with db.transaction() as conn:
            ids = [db.insert_trade(conn, "AAPL", "buy", i + 1, 100)["id"] for i in range(5)]
            assert [t["id"] for t in db.list_trades(conn)] == ids
            assert [t["id"] for t in db.list_trades(conn, limit=2)] == ids[-2:]


# --- snapshots ---------------------------------------------------------------


class TestSnapshots:
    def test_empty(self, db_path):
        with db.transaction() as conn:
            assert db.list_snapshots(conn) == []

    def test_insert_and_shape(self, db_path):
        with db.transaction() as conn:
            db.insert_snapshot(conn, 10000.0)
            snaps = db.list_snapshots(conn)
        assert len(snaps) == 1
        assert set(snaps[0]) == {"recorded_at", "total_value"}
        assert snaps[0]["total_value"] == 10000.0
        assert snaps[0]["recorded_at"].endswith("Z")

    def test_oldest_first_same_timestamp(self, db_path):
        with db.transaction() as conn:
            for v in [1.0, 2.0, 3.0]:
                db.insert_snapshot(conn, v)
            assert [s["total_value"] for s in db.list_snapshots(conn)] == [1.0, 2.0, 3.0]

    def test_oldest_first_by_timestamp(self, db_path):
        with db.transaction() as conn:
            rows = [("a", "2026-01-01T00:00:02Z", 2.0), ("b", "2026-01-01T00:00:01Z", 1.0)]
            conn.executemany(
                "INSERT INTO portfolio_snapshots (id, total_value, recorded_at) VALUES (?, ?, ?)",
                [(i, v, ts) for i, ts, v in rows],
            )
            assert [s["total_value"] for s in db.list_snapshots(conn)] == [1.0, 2.0]

    def test_limit_keeps_most_recent(self, db_path):
        with db.transaction() as conn:
            for v in range(1005):
                db.insert_snapshot(conn, float(v))
            snaps = db.list_snapshots(conn)
            assert len(snaps) == 1000
            assert snaps[0]["total_value"] == 5.0
            assert snaps[-1]["total_value"] == 1004.0
            small = db.list_snapshots(conn, limit=3)
            assert [s["total_value"] for s in small] == [1002.0, 1003.0, 1004.0]

    def test_user_isolation(self, db_path):
        with db.transaction() as conn:
            db.insert_snapshot(conn, 5.0, user_id="other")
            assert db.list_snapshots(conn) == []
            assert len(db.list_snapshots(conn, user_id="other")) == 1


# --- chat --------------------------------------------------------------------


class TestChat:
    def test_insert_user_message(self, db_path):
        with db.transaction() as conn:
            msg = db.insert_chat_message(conn, "user", "Buy 5 NVDA", None)
        assert set(msg) == {"id", "role", "content", "actions", "created_at"}
        assert msg["actions"] is None
        assert msg["role"] == "user"

    def test_actions_json_roundtrip(self, db_path):
        actions = [
            {"type": "trade", "ticker": "NVDA", "side": "buy", "quantity": 5,
             "status": "executed", "price": 890.1, "error": None},
            {"type": "watchlist", "ticker": "PYPL", "action": "add",
             "status": "failed", "error": "PYPL is already on the watchlist"},
        ]
        with db.transaction() as conn:
            msg = db.insert_chat_message(conn, "assistant", "Done", actions)
        with db.transaction() as conn:
            [stored] = db.list_chat_messages(conn)
            raw = conn.execute("SELECT actions FROM chat_messages").fetchone()[0]
        assert stored == msg
        assert stored["actions"] == actions
        assert isinstance(raw, str)

    def test_empty_actions_list_preserved(self, db_path):
        with db.transaction() as conn:
            db.insert_chat_message(conn, "assistant", "Hi", [])
            assert db.list_chat_messages(conn)[0]["actions"] == []

    def test_invalid_role_rejected(self, db_path):
        with db.transaction() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                db.insert_chat_message(conn, "system", "x", None)

    def test_order_and_limit(self, db_path):
        with db.transaction() as conn:
            for i in range(60):
                db.insert_chat_message(conn, "user" if i % 2 == 0 else "assistant", f"m{i}", None)
            msgs = db.list_chat_messages(conn)
            assert len(msgs) == 50
            assert msgs[0]["content"] == "m10"
            assert msgs[-1]["content"] == "m59"
            assert [m["content"] for m in db.list_chat_messages(conn, limit=20)] == [
                f"m{i}" for i in range(40, 60)
            ]

    def test_order_by_timestamp(self, db_path):
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO chat_messages (id, role, content, created_at) "
                "VALUES ('b', 'user', 'later', '2026-01-01T00:00:02Z'), "
                "('a', 'user', 'earlier', '2026-01-01T00:00:01Z')"
            )
            assert [m["content"] for m in db.list_chat_messages(conn)] == ["earlier", "later"]
