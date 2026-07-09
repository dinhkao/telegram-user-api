"""Phiếu TRẢ HÀNG (return_slips, app.db) — khách trả hàng, giảm công nợ.

KiotViet public API KHÔNG có POST /returns (đã thử 2026-07-09) → cơ chế: tạo HĐ
KiotViet GIÁ ÂM (sl dương × giá âm, KV chấp nhận, trừ thẳng nợ — số lượng âm thì
bị chặn). Bảng này là sổ phiếu trả phía app: items gốc (giá DƯƠNG, hiểu là trả),
link HĐ KV âm, snapshot nợ trước/sau (resync vá). Hiện trong feed khách
(server_app/customer_feed). Nối: utils.db. API: server_app/return_routes.py.
"""
from __future__ import annotations

import json

_SCHEMA = """
CREATE TABLE IF NOT EXISTS return_slips (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_key    TEXT    NOT NULL,          -- firebase_key khách
    thread_id       INTEGER,                   -- đơn gốc (tuỳ chọn)
    kv_invoice_id   INTEGER,                   -- HĐ KiotViet giá âm
    kv_invoice_code TEXT,
    items           TEXT    NOT NULL,          -- JSON [{sp, sl, price}] — giá DƯƠNG
    total           REAL    NOT NULL,          -- tổng tiền trả (DƯƠNG)
    note            TEXT,
    debt_before     REAL,                      -- nợ KV trước phiếu
    debt_after      REAL,                      -- nợ KV sau phiếu (resync vá)
    created_by      TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    deleted_at      TEXT,
    deleted_by      TEXT
);
"""
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_returns_customer ON return_slips(customer_key)",
    "CREATE INDEX IF NOT EXISTS idx_returns_thread   ON return_slips(thread_id)",
]


def ensure_returns_schema(conn) -> None:
    conn.executescript(_SCHEMA)
    for sql in _INDEXES:
        conn.execute(sql)
    conn.commit()


def _row_to_dict(r) -> dict:
    d = dict(r)
    try:
        d["items"] = json.loads(d.get("items") or "[]")
    except (TypeError, ValueError):
        d["items"] = []
    return d


def add_return(conn, customer_key: str, items: list[dict], total: float, *,
               note: str = "", thread_id=None, kv_invoice_id=None, kv_invoice_code=None,
               debt_before=None, debt_after=None, by: str = "") -> dict:
    ensure_returns_schema(conn)
    # created_at ISO giờ VN (+07:00) — cùng định dạng payment.created_at để feed
    # khách sort/hiển thị chung 1 trục thời gian (datetime('now') SQLite là UTC trần)
    from datetime import datetime, timezone, timedelta
    now_vn = datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO return_slips (customer_key, thread_id, kv_invoice_id, kv_invoice_code,"
        " items, total, note, debt_before, debt_after, created_by, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (str(customer_key), thread_id, kv_invoice_id, kv_invoice_code,
         json.dumps(items, ensure_ascii=False), float(total), note or "",
         debt_before, debt_after, by or "", now_vn))
    conn.commit()
    return get_return(conn, cur.lastrowid)


def get_return(conn, return_id: int) -> dict | None:
    ensure_returns_schema(conn)
    r = conn.execute("SELECT * FROM return_slips WHERE id = ?", (return_id,)).fetchone()
    return _row_to_dict(r) if r else None


def list_returns(conn, customer_key: str, include_deleted: bool = False) -> list[dict]:
    ensure_returns_schema(conn)
    where = "" if include_deleted else " AND deleted_at IS NULL"
    rows = conn.execute(
        f"SELECT * FROM return_slips WHERE customer_key = ?{where} ORDER BY created_at DESC, id DESC",
        (str(customer_key),)).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_all_returns(conn, limit: int = 20, offset: int = 0) -> list[dict]:
    """MỌI phiếu trả (mọi khách) mới→cũ, kèm tên khách — dashboard trả hàng."""
    ensure_returns_schema(conn)
    rows = conn.execute(
        "SELECT r.*, json_extract(c.json, '$.name') AS customer_name"
        " FROM return_slips r LEFT JOIN customers c ON c.firebase_key = r.customer_key"
        " WHERE r.deleted_at IS NULL ORDER BY r.created_at DESC, r.id DESC LIMIT ? OFFSET ?",
        (limit, offset)).fetchall()
    return [_row_to_dict(r) for r in rows]


def count_all_returns(conn) -> int:
    ensure_returns_schema(conn)
    return int(conn.execute("SELECT COUNT(*) FROM return_slips WHERE deleted_at IS NULL").fetchone()[0])


def get_return_full(conn, return_id: int) -> dict | None:
    """1 phiếu kèm tên khách (trang chi tiết)."""
    ensure_returns_schema(conn)
    r = conn.execute(
        "SELECT r.*, json_extract(c.json, '$.name') AS customer_name"
        " FROM return_slips r LEFT JOIN customers c ON c.firebase_key = r.customer_key"
        " WHERE r.id = ?", (return_id,)).fetchone()
    return _row_to_dict(r) if r else None


def set_return_invoice(conn, return_id: int, kv_id, kv_code, debt_before, debt_after) -> bool:
    """Gắn HĐ KiotViet (giá âm) vào phiếu nháp + snapshot nợ."""
    ensure_returns_schema(conn)
    conn.execute(
        "UPDATE return_slips SET kv_invoice_id = ?, kv_invoice_code = ?, debt_before = ?, debt_after = ? WHERE id = ?",
        (kv_id, kv_code, debt_before, debt_after, return_id))
    conn.commit()
    return True


def update_return_items(conn, return_id: int, items: list[dict], total: float, note: str) -> bool:
    """Sửa hàng trả/ghi chú — CHỈ khi phiếu còn NHÁP (chưa gắn HĐ KV, caller kiểm)."""
    ensure_returns_schema(conn)
    conn.execute(
        "UPDATE return_slips SET items = ?, total = ?, note = ? WHERE id = ?",
        (json.dumps(items, ensure_ascii=False), float(total), note or "", return_id))
    conn.commit()
    return True


def set_return_debt_after(conn, return_id: int, debt_after: float) -> bool:
    """Resync nền vá nợ-sau (KV eventual-consistent — như payment.new_debt)."""
    ensure_returns_schema(conn)
    conn.execute("UPDATE return_slips SET debt_after = ? WHERE id = ?", (float(debt_after), return_id))
    conn.commit()
    return True


def soft_delete_return(conn, return_id: int, by: str = "") -> bool:
    ensure_returns_schema(conn)
    conn.execute(
        "UPDATE return_slips SET deleted_at = datetime('now'), deleted_by = ? WHERE id = ? AND deleted_at IS NULL",
        (by or "", return_id))
    conn.commit()
    return True
