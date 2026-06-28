"""bot_don_hang/session_store.py — SQLite-backed persistence for in-progress sessions.

Sessions live in memory (store.py) but are persisted to SQLite so bot restarts
don't lose in-progress orders. On startup, call load_all() to restore.
"""
import json
import logging
import sqlite3
import time
from pathlib import Path

log = logging.getLogger("bot.session_store")

# Session store uses its own database, not the shared app.db
SESSION_DB = Path(__file__).resolve().parent.parent / "bot_sessions.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(SESSION_DB), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bot_sessions (
            chat_id INTEGER PRIMARY KEY,
            order_id TEXT NOT NULL,
            user_id INTEGER,
            thread_id INTEGER,
            data TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    conn.commit()


_connection: sqlite3.Connection | None = None


def _conn() -> sqlite3.Connection:
    global _connection
    if _connection is None:
        _connection = _connect()
        _ensure_table(_connection)
    return _connection


def _serialize(session) -> dict:
    """Convert a store.Session into JSON-serializable dict (drops non-serializable fields)."""
    return {
        "chat_id": session.chat_id,
        "order_id": session.order_id,
        "user_id": session.user_id,
        "thread_id": session.thread_id,
        "last_text": session.last_text,
        "invoice": list(session.invoice or []),
        "task_status": session.task_status,
        "customer_id": session.customer_id,
        "customer_name": session.customer_name,
        "kv_invoice_id": session.kv_invoice_id,
        "discount": session.discount,
        "pvc": session.pvc,
        "vat": session.vat,
        "kh_debt": session.kh_debt,
        "payments": list(session.payments or []),
        "discussion_group_message_id": session.discussion_group_message_id,
        "trello_card_id": session.trello_card_id,
    }


def save(session) -> None:
    if not session or not session.order_id:
        return
    try:
        data = json.dumps(_serialize(session), ensure_ascii=False)
        _conn().execute(
            "INSERT INTO bot_sessions(chat_id, order_id, user_id, thread_id, data, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET "
            "  order_id=excluded.order_id, user_id=excluded.user_id, "
            "  thread_id=excluded.thread_id, data=excluded.data, updated_at=excluded.updated_at",
            (session.chat_id, session.order_id, session.user_id, session.thread_id, data, int(time.time() * 1000)),
        )
        _conn().commit()
    except Exception as e:
        log.warning("save session chat=%s failed: %s", getattr(session, "chat_id", "?"), e)


def delete(chat_id: int) -> None:
    try:
        _conn().execute("DELETE FROM bot_sessions WHERE chat_id = ?", (chat_id,))
        _conn().commit()
    except Exception as e:
        log.warning("delete session chat=%s failed: %s", chat_id, e)


def load_all() -> list[dict]:
    """Return all persisted sessions, newest first."""
    try:
        rows = _conn().execute(
            "SELECT data FROM bot_sessions ORDER BY updated_at DESC"
        ).fetchall()
        return [json.loads(r[0]) for r in rows]
    except Exception as e:
        log.warning("load_all failed: %s", e)
        return []


def prune_older_than(seconds: int = 86400) -> int:
    """Delete sessions older than N seconds. Returns count deleted."""
    cutoff_ms = int((time.time() - seconds) * 1000)
    try:
        cur = _conn().execute("DELETE FROM bot_sessions WHERE updated_at < ?", (cutoff_ms,))
        _conn().commit()
        return cur.rowcount or 0
    except Exception as e:
        log.warning("prune failed: %s", e)
        return 0
