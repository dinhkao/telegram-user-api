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
    cols = {row[1] for row in conn.execute("PRAGMA table_info(purchase_slips)")}
    if "payments" not in cols:   # 2026-07-14: trả tiền NCC từ két (JSON list)
        conn.execute("ALTER TABLE purchase_slips ADD COLUMN payments TEXT")
    # 2026-07-16: nhập kho hàng mua về (thùng có sẵn / thùng mới) — như hàng trả
    for name in ("goods_handled_at", "goods_handled_by", "goods_result"):
        if name not in cols:
            conn.execute(f"ALTER TABLE purchase_slips ADD COLUMN {name} TEXT")
    conn.commit()


def _row_to_dict(r) -> dict:
    from purchase_store.payments import _parse, paid_total
    d = dict(r)
    try:
        d["items"] = json.loads(d.get("items") or "[]")
    except (TypeError, ValueError):
        d["items"] = []
    d["payments"] = _parse(d.get("payments"))
    d["paid"] = paid_total(d["payments"])
    if d.get("goods_result"):
        try:
            d["goods_result"] = json.loads(d["goods_result"])
        except (TypeError, ValueError):
            d["goods_result"] = None
    # remaining tính 1 chỗ (Python round) — client hiển thị thẳng, khỏi lệch
    # Math.round(JS) vs round(Python) khi total lẻ
    d["remaining"] = int(round(float(d.get("total") or 0))) - d["paid"]
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
                          note: str, supplier_id: int | None = None) -> tuple[bool, str]:
    """Sửa hàng nhập/ghi chú (văn phòng) — đổi cả NCC nếu truyền supplier_id.
    CHẶN hạ tổng xuống dưới số ĐÃ TRẢ NCC (cùng transaction, tránh race với trả
    tiền đồng thời) — không thì phiếu trả-dư bị che thành 'đã trả đủ'."""
    from purchase_store.payments import _parse, paid_total
    from utils.db import transaction
    ensure_purchases_schema(conn)
    with transaction(conn):
        r = conn.execute(
            "SELECT payments, supplier_id FROM purchase_slips WHERE id = ?", (purchase_id,)).fetchone()
        paid = paid_total(_parse(r["payments"])) if r else 0
        if int(round(float(total))) < paid:
            return False, (f"Phiếu đã trả {paid:,}đ — tổng mới không được thấp hơn số đã trả"
                           .replace(",", "."))
        # Đã trả tiền NCC → không được đổi sang NCC khác (các lần trả gắn với NCC cũ
        # sẽ lệch két/công nợ). Muốn đổi thì gỡ hết các lần trả trước.
        cur_sup = r["supplier_id"] if r else None
        if (paid > 0 and supplier_id is not None and cur_sup is not None
                and int(supplier_id) != int(cur_sup)):
            return False, "Phiếu đã trả tiền NCC — không đổi nhà cung cấp được (gỡ các lần trả trước)"
        if supplier_id is not None:
            conn.execute(
                "UPDATE purchase_slips SET items = ?, total = ?, note = ?, supplier_id = ? WHERE id = ?",
                (json.dumps(items, ensure_ascii=False), float(total), note or "", int(supplier_id), purchase_id))
        else:
            conn.execute(
                "UPDATE purchase_slips SET items = ?, total = ?, note = ? WHERE id = ?",
                (json.dumps(items, ensure_ascii=False), float(total), note or "", purchase_id))
    return True, ""


def claim_goods_handling(conn, purchase_id: int, by: str = "") -> bool:
    """GIÀNH quyền nhập kho hàng mua về (compare-and-set nguyên tử) — đặt
    goods_handled_at CHỈ khi còn NULL. False = đã có người nhập (chặn 2 request
    đồng thời double-apply vào kho). Gọi TRƯỚC khi thao tác kho."""
    ensure_purchases_schema(conn)
    cur = conn.execute(
        "UPDATE purchase_slips SET goods_handled_at = ?, goods_handled_by = ? "
        "WHERE id = ? AND goods_handled_at IS NULL",
        (_now_vn(), by or "", purchase_id))
    conn.commit()
    return cur.rowcount == 1


def clear_goods_handling(conn, purchase_id: int) -> bool:
    """HỦY CHỐT nhập kho: xoá dấu goods_handled_* + goods_result → phiếu sửa lại
    được, nhập kho lại được. Caller (purchase_goods.undo_purchase_receipt) phải
    hoàn kho TRƯỚC (xoá thùng mới / gỡ allocation purchase_in)."""
    ensure_purchases_schema(conn)
    conn.execute(
        "UPDATE purchase_slips SET goods_handled_at = NULL, goods_handled_by = NULL, goods_result = NULL"
        " WHERE id = ?", (purchase_id,))
    conn.commit()
    return True


def set_goods_result(conn, purchase_id: int, result: dict) -> bool:
    """Lưu tóm tắt kết quả nhập kho (sau khi đã giành quyền + thao tác xong).
    result = {restocked_existing:[], restocked_new:[], skipped:[]}."""
    ensure_purchases_schema(conn)
    conn.execute("UPDATE purchase_slips SET goods_result = ? WHERE id = ?",
                 (json.dumps(result, ensure_ascii=False), purchase_id))
    conn.commit()
    return True


def soft_delete_purchase(conn, purchase_id: int, by: str = "") -> bool:
    ensure_purchases_schema(conn)
    conn.execute(
        "UPDATE purchase_slips SET deleted_at = datetime('now', '+7 hours'), deleted_by = ?"
        " WHERE id = ? AND deleted_at IS NULL", (by or "", purchase_id))
    conn.commit()
    return True


from purchase_store.payments import (add_purchase_payment, delete_purchase_payment,  # noqa: E402,F401
                                     paid_total, payments_for_cashbox)
