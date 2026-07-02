from __future__ import annotations

import json
import logging
import sqlite3

from server_app.config import SHARED_DB_PATH
from utils.db import get_connection
from vn import vn_normalize

log = logging.getLogger("server")
_orders_fts_ready = False
_fts_last_updated_at = 0   # max(orders.updated_at) đã index — mốc cho sync tăng dần


def get_orders_conn():
    return get_connection(SHARED_DB_PATH, autocommit=False, busy_timeout=5000)


def _fts_content(json_text: str) -> str | None:
    try:
        j = json.loads(json_text)
        raw = " ".join([j.get("customer_name", ""), j.get("text", ""), j.get("text_raw", ""), j.get("kiotvietInvoiceCode", ""), str(j.get("firebase_key", "")), str(j.get("thread_id", "")), " ".join(it.get("sp", "") for it in (j.get("invoice") or []))])
        return vn_normalize(raw)
    except Exception:
        return None


def ensure_orders_fts(conn):
    global _orders_fts_ready, _fts_last_updated_at
    if _orders_fts_ready:
        _sync_orders_fts(conn)
        return
    try:
        from utils.db import IS_POSTGRES
        conn.execute("DROP TABLE IF EXISTS orders_fts")
        if IS_POSTGRES:
            # PG không có fts5; orders_fts vốn chỉ query bằng LIKE nên dùng bảng thường.
            conn.execute("CREATE TABLE orders_fts (thread_id bigint, content text)")
        else:
            conn.execute("CREATE VIRTUAL TABLE orders_fts USING fts5(thread_id UNINDEXED, content, tokenize='trigram')")
        rows = conn.execute("SELECT thread_id, json, updated_at FROM orders WHERE deleted_at IS NULL AND json IS NOT NULL").fetchall()
        for r in rows:
            content = _fts_content(r["json"])
            if content is not None:
                conn.execute("INSERT INTO orders_fts(thread_id, content) VALUES(?, ?)", (r["thread_id"], content))
            if r["updated_at"] and r["updated_at"] > _fts_last_updated_at:
                _fts_last_updated_at = r["updated_at"]
        conn.commit()
        _orders_fts_ready = True
    except Exception as e:
        log.warning("orders_fts setup failed: %s", e)


def _sync_orders_fts(conn):
    """Index tăng dần các đơn mới/sửa từ lần index trước — trước đây FTS chỉ build
    1 lần mỗi process nên đơn tạo sau đó tìm không ra cho tới khi restart."""
    global _fts_last_updated_at
    try:
        rows = conn.execute(
            "SELECT thread_id, json, updated_at FROM orders WHERE updated_at > ? AND deleted_at IS NULL AND json IS NOT NULL",
            (_fts_last_updated_at,),
        ).fetchall()
        if not rows:
            return
        for r in rows:
            content = _fts_content(r["json"])
            conn.execute("DELETE FROM orders_fts WHERE thread_id = ?", (r["thread_id"],))
            if content is not None:
                conn.execute("INSERT INTO orders_fts(thread_id, content) VALUES(?, ?)", (r["thread_id"], content))
            if r["updated_at"] and r["updated_at"] > _fts_last_updated_at:
                _fts_last_updated_at = r["updated_at"]
        conn.commit()
    except Exception as e:
        log.warning("orders_fts sync failed: %s", e)


def search_orders_fts(conn, query: str):
    if not _orders_fts_ready:
        return None
    try:
        rows = conn.execute("SELECT thread_id FROM orders_fts WHERE content LIKE ? LIMIT 500", (f"%{vn_normalize(query)}%",)).fetchall()
        return [r["thread_id"] for r in rows] if rows else [-1]
    except Exception as e:
        log.warning("orders_fts search failed: %s", e)
        return None
