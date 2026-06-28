"""bot_don_hang/db.py — SQLite access mirroring final_telegram schema."""
import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot_core.config import DB_PATH

_db_local = threading.local()


def _conn():
    if not hasattr(_db_local, "conn") or _db_local.conn is None:
        _db_local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _db_local.conn.execute("PRAGMA journal_mode = WAL")
        _db_local.conn.execute("PRAGMA synchronous = NORMAL")
        _db_local.conn.execute("PRAGMA foreign_keys = ON")
        _db_local.conn.execute("PRAGMA busy_timeout = 5000")
    return _db_local.conn


def get_order(key: str) -> dict | None:
    row = _conn().execute(
        "SELECT json FROM orders WHERE firebase_key = ? AND deleted_at IS NULL",
        (key,),
    ).fetchone()
    return json.loads(row[0]) if row else None


def get_order_by_thread(thread_id: int) -> dict | None:
    row = _conn().execute(
        "SELECT json FROM orders WHERE thread_id = ? AND deleted_at IS NULL",
        (thread_id,),
    ).fetchone()
    return json.loads(row[0]) if row else None


def get_orders_without_giao(limit: int = 5) -> list[dict]:
    """Get last N orders that do NOT have giao_hang task completed.

    Filters out test orders and orders with no text.
    Sorts by thread_id DESC for real orders.
    """
    rows = _conn().execute(
        "SELECT json FROM orders WHERE deleted_at IS NULL "
        "AND thread_id IS NOT NULL "
        "AND thread_id < 1000000000 "
        "AND json_extract(json, '$.text') IS NOT NULL "
        "AND json_extract(json, '$.text') != '' "
        "AND lower(json_extract(json, '$.text')) NOT LIKE 'test%' "
        "AND (json_extract(json, '$.task_status.giao_hang.done') IS NULL "
        "     OR json_extract(json, '$.task_status.giao_hang.done') != 1) "
        "ORDER BY thread_id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [json.loads(r[0]) for r in rows if r]


def get_orders_without_giao_paginated(page: int = 1, per_page: int = 10, days: int = 30) -> tuple[list[dict], int]:
    """Get orders without giao_hang completed, created in the last N days.
    Returns (orders, total_count) for pagination.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    base = (
        "FROM orders WHERE deleted_at IS NULL "
        "AND thread_id IS NOT NULL "
        "AND thread_id < 1000000000 "
        "AND json_extract(json, '$.text') IS NOT NULL "
        "AND json_extract(json, '$.text') != '' "
        "AND lower(json_extract(json, '$.text')) NOT LIKE 'test%' "
        "AND json_extract(json, '$.created') >= ? "
        "AND (json_extract(json, '$.task_status.giao_hang.done') IS NULL "
        "     OR json_extract(json, '$.task_status.giao_hang.done') != 1) "
    )
    conn = _conn()
    total = conn.execute(f"SELECT COUNT(*) {base}", (cutoff,)).fetchone()[0]
    rows = conn.execute(
        f"SELECT json {base} ORDER BY thread_id DESC LIMIT ? OFFSET ?",
        (cutoff, per_page, (page - 1) * per_page),
    ).fetchall()
    return [json.loads(r[0]) for r in rows if r], total


def get_orders_without_nop(page: int = 1, per_page: int = 10) -> tuple[list[dict], int]:
    """Get orders where nop_tien OR nhan_tien is NOT done, created after 2026-04-01.
    Returns (orders, total_count) for pagination.
    """
    base = (
        "FROM orders WHERE deleted_at IS NULL "
        "AND thread_id IS NOT NULL "
        "AND thread_id < 1000000000 "
        "AND json_extract(json, '$.text') IS NOT NULL "
        "AND json_extract(json, '$.text') != '' "
        "AND lower(json_extract(json, '$.text')) NOT LIKE 'test%' "
        "AND json_extract(json, '$.created') >= '2026-04-01' "
        "AND ("
        "     json_extract(json, '$.task_status.nop_tien.done') IS NULL "
        "     OR json_extract(json, '$.task_status.nop_tien.done') != 1 "
        "     OR json_extract(json, '$.task_status.nhan_tien.done') IS NULL "
        "     OR json_extract(json, '$.task_status.nhan_tien.done') != 1"
        ") "
    )
    conn = _conn()
    total = conn.execute(f"SELECT COUNT(*) {base}").fetchone()[0]
    rows = conn.execute(
        f"SELECT json {base} ORDER BY thread_id DESC LIMIT ? OFFSET ?",
        (per_page, (page - 1) * per_page),
    ).fetchall()
    return [json.loads(r[0]) for r in rows if r], total


def search_orders(keyword: str, page: int = 1, per_page: int = 10) -> tuple[list[dict], int]:
    """Search orders by keyword (accent-insensitive) created after 2026-04-01.
    Returns (orders, total_count) for pagination.
    """
    from bot_core.utils import _norm
    norm_kw = _norm(keyword)
    conn = _conn()
    rows = conn.execute(
        "SELECT json FROM orders WHERE deleted_at IS NULL "
        "AND thread_id IS NOT NULL "
        "AND json_extract(json, '$.text') IS NOT NULL "
        "AND json_extract(json, '$.text') != '' "
        "AND json_extract(json, '$.created') >= '2026-04-01' "
        "ORDER BY thread_id DESC"
    ).fetchall()
    # Filter in Python for accent-insensitive matching
    matched = []
    for r in rows:
        o = json.loads(r[0])
        text = o.get("text", "")
        if norm_kw in _norm(text):
            matched.append(o)
    total = len(matched)
    start = (page - 1) * per_page
    return matched[start:start + per_page], total


def get_customer_by_key(key: str) -> dict | None:
    row = _conn().execute(
        "SELECT json FROM customers WHERE firebase_key = ? AND deleted_at IS NULL",
        (key,),
    ).fetchone()
    return json.loads(row[0]) if row else None


def get_kv(path: str):
    row = _conn().execute(
        "SELECT value FROM kv_store WHERE path = ?", (path,)
    ).fetchone()
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
        "ON CONFLICT(path) DO UPDATE SET rev = rev + 1",
        (path,),
    )
    _conn().commit()


def clear_task_status(order_id: str, key: str) -> bool:
    """Clear a single task entry from task_status JSON in SQLite."""
    order = get_order(order_id)
    if not order:
        return False
    ts = order.get("task_status") or {}
    if key not in ts:
        return False
    # Remove the task entry entirely
    del ts[key]
    order["task_status"] = ts
    # Write back
    _conn().execute(
        "UPDATE orders SET json = ?, updated_at = ? WHERE firebase_key = ?",
        (json.dumps(order, ensure_ascii=False), int(time.time() * 1000), order_id),
    )
    _conn().commit()
    bump_rev(f"donhang_new_chuaxong/{order_id}")
    return True
