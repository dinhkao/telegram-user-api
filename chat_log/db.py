from __future__ import annotations

import logging
import os
import sqlite3

log = logging.getLogger("chat_logger")
from utils.paths import SHARED_DB_PATH
from utils.db import get_connection
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS order_chat_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id    INTEGER NOT NULL,
    message_id   INTEGER NOT NULL UNIQUE,
    sender_id    INTEGER,
    sender_name  TEXT,
    text         TEXT,
    media_type   TEXT,
    event_type   TEXT DEFAULT 'new',
    raw_json     TEXT,
    created_at   TEXT DEFAULT (datetime('now')),
    edited_at    TEXT,
    deleted_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_chat_thread ON order_chat_messages(thread_id);
"""


def connect_db() -> sqlite3.Connection:
    return get_connection(SHARED_DB_PATH, autocommit=False, busy_timeout=3000)


def table_columns(conn: sqlite3.Connection) -> set[str]:
    cur = conn.execute("PRAGMA table_info(order_chat_messages)")
    return {row[1] for row in cur.fetchall()}


def migrate_table(conn: sqlite3.Connection) -> None:
    columns = table_columns(conn)
    added_columns: list[str] = []
    for name, sql in [
        ("event_type", "ALTER TABLE order_chat_messages ADD COLUMN event_type TEXT DEFAULT 'new'"),
        ("raw_json", "ALTER TABLE order_chat_messages ADD COLUMN raw_json TEXT"),
        ("edited_at", "ALTER TABLE order_chat_messages ADD COLUMN edited_at TEXT"),
        ("deleted_at", "ALTER TABLE order_chat_messages ADD COLUMN deleted_at TEXT"),
    ]:
        if name not in columns:
            conn.execute(sql)
            added_columns.append(name)
    conn.execute(
        "UPDATE order_chat_messages SET event_type = 'new' "
        "WHERE event_type IS NULL AND deleted_at IS NULL"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_thread ON order_chat_messages(thread_id)")
    conn.commit()
    if added_columns:
        log.info("order_chat_messages migrated: added columns %s", ", ".join(added_columns))


def init_table() -> None:
    from utils.db import IS_POSTGRES
    conn = connect_db()
    try:
        if not IS_POSTGRES:  # trên PG bảng do migrations/pg/0001_init.sql tạo (AUTOINCREMENT là SQLite)
            conn.executescript(_SCHEMA_SQL)
        migrate_table(conn)
    finally:
        conn.close()
    log.info("order_chat_messages table ready")
