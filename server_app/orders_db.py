from __future__ import annotations

import json
import logging
import sqlite3

from server_app.config import SHARED_DB_PATH
from vn import vn_normalize

log = logging.getLogger("server")
_orders_fts_ready = False


def get_orders_conn():
    conn = sqlite3.connect(SHARED_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def ensure_orders_fts(conn):
    global _orders_fts_ready
    if _orders_fts_ready:
        return
    try:
        conn.execute("DROP TABLE IF EXISTS orders_fts")
        conn.execute("CREATE VIRTUAL TABLE orders_fts USING fts5(thread_id UNINDEXED, content, tokenize='trigram')")
        rows = conn.execute("SELECT thread_id, json FROM orders WHERE deleted_at IS NULL AND json IS NOT NULL").fetchall()
        for r in rows:
            try:
                j = json.loads(r["json"])
                raw = " ".join([j.get("customer_name", ""), j.get("text", ""), j.get("text_raw", ""), j.get("kiotvietInvoiceCode", ""), str(j.get("firebase_key", "")), str(j.get("thread_id", "")), " ".join(it.get("sp", "") for it in (j.get("invoice") or []))])
                conn.execute("INSERT INTO orders_fts(thread_id, content) VALUES(?, ?)", (r["thread_id"], vn_normalize(raw)))
            except Exception:
                pass
        conn.commit()
        _orders_fts_ready = True
    except Exception as e:
        log.warning("orders_fts setup failed: %s", e)


def search_orders_fts(conn, query: str):
    if not _orders_fts_ready:
        return None
    try:
        rows = conn.execute("SELECT thread_id FROM orders_fts WHERE content LIKE ? LIMIT 500", (f"%{vn_normalize(query)}%",)).fetchall()
        return [r["thread_id"] for r in rows] if rows else [-1]
    except Exception as e:
        log.warning("orders_fts search failed: %s", e)
        return None
