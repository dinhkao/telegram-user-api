"""Phiếu NHẬP HÀNG (purchase_slips, app.db) — nhập hàng từ nhà cung cấp.

100% local, KHÔNG dính KiotViet. Flow giống ĐƠN: tạo phiếu (sửa được, văn phòng)
→ xoá = admin (xoá mềm). Hàng hoá DÙNG CHUNG bảng sản phẩm: items JSON
[{sp, sp_id?, sl, price}] — sp_id gắn khi mã resolve được (product_store), giá là
snapshot. Nối: utils.db, supplier_store (JOIN tên NCC).
API: server_app/purchase_routes.py.
"""
from __future__ import annotations

import json

_SCHEMA = """
CREATE TABLE IF NOT EXISTS purchase_slips (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id  INTEGER NOT NULL,
    items        TEXT    NOT NULL,          -- JSON [{sp, sp_id?, sl, price}]
    total        REAL    NOT NULL,
    note         TEXT,
    created_by   TEXT,
    created_at   TEXT,
    deleted_at   TEXT,
    deleted_by   TEXT
);
"""
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_purchases_supplier ON purchase_slips(supplier_id)",
]


def ensure_purchases_schema(conn) -> None:
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


def _now_vn() -> str:
    # ISO giờ VN (+07:00) — cùng định dạng return_slips để sort/hiển thị nhất quán
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")


def add_purchase(conn, supplier_id: int, items: list[dict], total: float, *,
                 note: str = "", by: str = "") -> dict:
    ensure_purchases_schema(conn)
    cur = conn.execute(
        "INSERT INTO purchase_slips (supplier_id, items, total, note, created_by, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (int(supplier_id), json.dumps(items, ensure_ascii=False), float(total),
         note or "", by or "", _now_vn()))
    conn.commit()
    return get_purchase(conn, cur.lastrowid)


def get_purchase(conn, purchase_id: int) -> dict | None:
    ensure_purchases_schema(conn)
    r = conn.execute("SELECT * FROM purchase_slips WHERE id = ?", (purchase_id,)).fetchone()
    return _row_to_dict(r) if r else None


def get_purchase_full(conn, purchase_id: int) -> dict | None:
    """1 phiếu kèm tên NCC (trang chi tiết)."""
    ensure_purchases_schema(conn)
    from supplier_store import ensure_suppliers_schema
    ensure_suppliers_schema(conn)
    r = conn.execute(
        "SELECT p.*, s.name AS supplier_name FROM purchase_slips p"
        " LEFT JOIN suppliers s ON s.id = p.supplier_id WHERE p.id = ?",
        (purchase_id,)).fetchone()
    return _row_to_dict(r) if r else None


def list_all_purchases(conn, limit: int = 20, offset: int = 0) -> list[dict]:
    """MỌI phiếu nhập mới→cũ, kèm tên NCC — dashboard nhập hàng."""
    ensure_purchases_schema(conn)
    from supplier_store import ensure_suppliers_schema
    ensure_suppliers_schema(conn)
    rows = conn.execute(
        "SELECT p.*, s.name AS supplier_name FROM purchase_slips p"
        " LEFT JOIN suppliers s ON s.id = p.supplier_id"
        " WHERE p.deleted_at IS NULL ORDER BY p.created_at DESC, p.id DESC LIMIT ? OFFSET ?",
        (limit, offset)).fetchall()
    return [_row_to_dict(r) for r in rows]


def count_all_purchases(conn) -> int:
    ensure_purchases_schema(conn)
    return int(conn.execute(
        "SELECT COUNT(*) FROM purchase_slips WHERE deleted_at IS NULL").fetchone()[0])


def list_purchases_for_supplier(conn, supplier_id: int) -> list[dict]:
    """Mọi phiếu nhập của 1 NCC mới→cũ (trang chi tiết NCC)."""
    ensure_purchases_schema(conn)
    rows = conn.execute(
        "SELECT * FROM purchase_slips WHERE supplier_id = ? AND deleted_at IS NULL"
        " ORDER BY created_at DESC, id DESC", (int(supplier_id),)).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_purchase_items(conn, purchase_id: int, items: list[dict], total: float,
                          note: str, supplier_id: int | None = None) -> bool:
    """Sửa hàng nhập/ghi chú (văn phòng) — đổi cả NCC nếu truyền supplier_id."""
    ensure_purchases_schema(conn)
    if supplier_id is not None:
        conn.execute(
            "UPDATE purchase_slips SET items = ?, total = ?, note = ?, supplier_id = ? WHERE id = ?",
            (json.dumps(items, ensure_ascii=False), float(total), note or "", int(supplier_id), purchase_id))
    else:
        conn.execute(
            "UPDATE purchase_slips SET items = ?, total = ?, note = ? WHERE id = ?",
            (json.dumps(items, ensure_ascii=False), float(total), note or "", purchase_id))
    conn.commit()
    return True


def soft_delete_purchase(conn, purchase_id: int, by: str = "") -> bool:
    ensure_purchases_schema(conn)
    conn.execute(
        "UPDATE purchase_slips SET deleted_at = datetime('now', '+7 hours'), deleted_by = ?"
        " WHERE id = ? AND deleted_at IS NULL", (by or "", purchase_id))
    conn.commit()
    return True
