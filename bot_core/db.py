"""bot_core/db.py — truy cập app.db (SQLite hoặc Postgres) qua cổng utils.db."""
import json, threading, time
from pathlib import Path
from bot_core.config import DB_PATH
from utils.db import get_connection, IS_POSTGRES

_db_local = threading.local()

def _conn():
    if not hasattr(_db_local, "conn") or _db_local.conn is None:
        # autocommit OFF (như cũ: không đặt isolation_level, dùng commit() tường minh).
        conn = get_connection(str(DB_PATH), autocommit=False)
        if not IS_POSTGRES:
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA foreign_keys = ON")
        _db_local.conn = conn
        _migrate(conn)
    return _db_local.conn


def _migrate(conn):
    if IS_POSTGRES:
        return  # schema từ migrations/pg/0001_init.sql là nguồn; generated cols đã có.
    # Generated columns (hidden=2) only seen in table_xinfo, not table_info
    hidden = [r[1] for r in conn.execute("PRAGMA table_xinfo(orders)").fetchall() if r[6] == 2]
    if "nop_nhan_done" not in hidden:
        conn.executescript("""
            ALTER TABLE orders ADD COLUMN nop_nhan_done INTEGER
                GENERATED ALWAYS AS (
                    CASE WHEN json_extract(json, '$.task_status.nop_tien.done') = 1
                           AND json_extract(json, '$.task_status.nhan_tien.done') = 1
                    THEN 1 ELSE 0 END
                ) VIRTUAL;
            ALTER TABLE orders ADD COLUMN order_created TEXT
                GENERATED ALWAYS AS (json_extract(json, '$.created')) VIRTUAL;
            CREATE INDEX IF NOT EXISTS idx_orders_nop_nhan
                ON orders(nop_nhan_done, order_created)
                WHERE deleted_at IS NULL;
        """)
        conn.commit()

def _fetch_one(sql, params=()):
    row = _conn().execute(sql, params).fetchone()
    return json.loads(row[0]) if row else None

def get_order(key: str) -> dict | None:
    return _fetch_one("SELECT json FROM orders WHERE firebase_key = ? AND deleted_at IS NULL", (key,))

def get_order_by_thread(thread_id: int) -> dict | None:
    return _fetch_one("SELECT json FROM orders WHERE thread_id = ? AND deleted_at IS NULL", (thread_id,))

def get_customer_by_key(key: str) -> dict | None:
    return _fetch_one("SELECT json FROM customers WHERE firebase_key = ? AND deleted_at IS NULL", (key,))

def get_kv(path: str):
    row = _conn().execute("SELECT value FROM kv_store WHERE path = ?", (path,)).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None

def set_kv(path: str, value):
    _conn().execute(
        "INSERT INTO kv_store(path, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(path) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (path, json.dumps(value), int(time.time() * 1000)),
    )
    _conn().commit()

def bump_rev(path: str):
    _conn().execute(
        "INSERT INTO kv_revisions(path, rev) VALUES (?, 1) "
        # qualify bảng: PG coi `rev` trần là mơ hồ; SQLite cũng chấp nhận dạng này.
        "ON CONFLICT(path) DO UPDATE SET rev = kv_revisions.rev + 1", (path,))
    _conn().commit()

def clear_task_status(order_id: str, key: str) -> bool:
    order = get_order(order_id)
    if not order:
        return False
    ts = order.get("task_status") or {}
    if key not in ts:
        return False
    del ts[key]
    order["task_status"] = ts
    _conn().execute("UPDATE orders SET json = ?, updated_at = ? WHERE firebase_key = ?",
        (json.dumps(order, ensure_ascii=False), int(time.time() * 1000), order_id))
    _conn().commit()
    bump_rev(f"donhang_new_chuaxong/{order_id}")
    return True

# Re-export query functions for backward compatibility
def get_orders_without_giao(limit=5):
    from bot_core.db_queries import get_orders_without_giao as _q
    return _q(_conn(), limit)

def get_orders_without_giao_paginated(page=1, per_page=10, days=30):
    from bot_core.db_queries import get_orders_without_giao_paginated as _q
    return _q(_conn(), page, per_page, days)

def get_orders_without_nop(page=1, per_page=10):
    from bot_core.db_queries import get_orders_without_nop as _q
    return _q(_conn(), page, per_page)

def search_orders(keyword, page=1, per_page=10):
    from bot_core.db_queries import search_orders as _q
    return _q(_conn(), keyword, page, per_page)
