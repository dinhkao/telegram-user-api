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
_stats_cols_ready = False


def get_orders_conn():
    return get_connection(SHARED_DB_PATH, autocommit=False, busy_timeout=5000)


def ensure_orders_stats_columns(conn):
    """Cột generated + index cho việc load danh sách đơn (SQLite).

    Không có index: mỗi lần load trang 1 vừa quét toàn bảng đếm 3 chip
    (~66ms/17k đơn) vừa TEMP B-TREE sort toàn bảng cho ORDER BY (~59ms).
    Có index (has_customer,is_done) + (has_customer,order_created,thread_id):
    đếm + sắp xếp bằng index → <1ms. PG đã sẵn has_customer (migrations/pg).
    Cột VIRTUAL không tốn chỗ. Chạy 1 lần/process; index tạo idempotent nên vẫn
    được bổ sung kể cả khi cột đã có từ lần chạy trước."""
    global _stats_cols_ready
    if _stats_cols_ready:
        return
    try:
        from utils.db import IS_POSTGRES
        if IS_POSTGRES:
            _stats_cols_ready = True
            return
        hidden = [r[1] for r in conn.execute("PRAGMA table_xinfo(orders)").fetchall() if r[6] == 2]
        if "has_customer" not in hidden:
            conn.executescript("""
                ALTER TABLE orders ADD COLUMN has_customer INTEGER
                    GENERATED ALWAYS AS (
                        CASE WHEN (json_extract(json, '$.hoadon.print_content.kh') IS NOT NULL
                                   AND json_extract(json, '$.hoadon.print_content.kh') != '')
                               OR (json_extract(json, '$.customer_name') IS NOT NULL
                                   AND json_extract(json, '$.customer_name') != '')
                        THEN 1 ELSE 0 END
                    ) VIRTUAL;
                ALTER TABLE orders ADD COLUMN is_done INTEGER
                    GENERATED ALWAYS AS (
                        CASE WHEN json_extract(json, '$.done_after_20250124') = 1 THEN 1 ELSE 0 END
                    ) VIRTUAL;
            """)
            conn.commit()
        # Index tạo ngoài guard cột → bổ sung được cả khi cột đã tồn tại sẵn.
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_orders_stats
                ON orders(has_customer, is_done)
                WHERE deleted_at IS NULL;
            CREATE INDEX IF NOT EXISTS idx_orders_list
                ON orders(has_customer DESC, order_created DESC, thread_id DESC)
                WHERE deleted_at IS NULL;
            CREATE INDEX IF NOT EXISTS idx_orders_created_tid
                ON orders(order_created DESC, thread_id DESC)
                WHERE deleted_at IS NULL;
        """)
        conn.commit()
        _stats_cols_ready = True
    except Exception as e:
        log.warning("ensure_orders_stats_columns failed: %s", e)


def prewarm_orders_indexes():
    """Dựng sẵn FTS + cột/index stats lúc khởi động (chạy trong thread nền).

    FTS build lần đầu tốn ~460ms/17k đơn — nếu để lười tới lần search đầu thì
    người dùng phải chờ. Gọi ở bootstrap qua asyncio.to_thread để không chặn
    event loop. Set cờ _orders_fts_ready toàn process → request sau chỉ sync."""
    try:
        conn = get_orders_conn()
        try:
            ensure_orders_stats_columns(conn)
            ensure_orders_fts(conn)
            log.info("orders indexes prewarmed (FTS + stats cols)")
        finally:
            conn.close()
    except Exception as e:
        log.warning("prewarm_orders_indexes failed: %s", e)


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
        # ORDER BY thread_id DESC: nếu >500 kết quả, giữ 500 đơn MỚI NHẤT (thread_id
        # tăng dần theo thời gian) thay vì 500 tuỳ ý → không rớt đơn mới. Danh sách
        # cuối vẫn được orders_api sắp theo order_created DESC.
        rows = conn.execute("SELECT thread_id FROM orders_fts WHERE content LIKE ? ORDER BY thread_id DESC LIMIT 500", (f"%{vn_normalize(query)}%",)).fetchall()
        return [r["thread_id"] for r in rows] if rows else [-1]
    except Exception as e:
        log.warning("orders_fts search failed: %s", e)
        return None
