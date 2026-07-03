"""CRUD kho thùng (inventory_boxes) — IO + transaction, không chứa logic thuần.

Mọi mutation nhiều-bước bọc `transaction(conn)` (BEGIN IMMEDIATE) để 2 người
nhập/xuất cùng lúc không sinh trùng mã hoặc xuất trùng thùng. Mã thùng do
inventory_store.domain sinh. Nối: utils.db, inventory_store.domain.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta

from utils.db import transaction
from .domain import next_box_code

_VN_TZ = timezone(timedelta(hours=7))


def _now() -> str:
    return datetime.now(_VN_TZ).isoformat(timespec="seconds")


def add_boxes(conn, product_code, quantities, *, source_thread_id=None, by=None, note=None) -> list[dict]:
    """Tạo N thùng mới cho product (mã tự sinh tuần tự, nguyên tử). Trả list box dict."""
    code = str(product_code).strip().upper()
    created: list[dict] = []
    with transaction(conn):
        rows = conn.execute(
            "SELECT box_code FROM inventory_boxes WHERE product_code = ?", (code,)
        ).fetchall()
        existing = [r[0] for r in rows]
        now = _now()
        for q in quantities:
            box_code = next_box_code(code, existing)
            existing.append(box_code)
            cur = conn.execute(
                "INSERT INTO inventory_boxes "
                "(product_code, box_code, quantity, status, source_thread_id, note, created_at, created_by) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (code, box_code, float(q), "in_stock", source_thread_id, note or "", now, by or ""),
            )
            created.append({
                "id": cur.lastrowid, "product_code": code, "box_code": box_code,
                "quantity": float(q), "status": "in_stock",
                "source_thread_id": source_thread_id, "created_at": now, "created_by": by or "",
            })
    return created


def list_boxes(conn, *, product_code=None, status=None, source_thread_id=None,
               order_thread_id=None, active_only=False) -> list[dict]:
    """Liệt kê thùng theo bộ lọc (product/status/slip nguồn/đơn). Sắp theo mã thùng.

    active_only=True → chỉ thùng còn hiệu lực (bỏ thùng bị vô hiệu) — dùng cho tồn
    kho / khả dụng phân bổ. Mặc định trả cả thùng vô hiệu (để hiển thị mờ).
    """
    where, params = [], []
    if product_code:
        where.append("product_code = ?"); params.append(str(product_code).strip().upper())
    if status:
        where.append("status = ?"); params.append(status)
    if source_thread_id is not None:
        where.append("source_thread_id = ?"); params.append(source_thread_id)
    if order_thread_id is not None:
        where.append("order_thread_id = ?"); params.append(order_thread_id)
    if active_only:
        where.append("(disabled IS NULL OR disabled = 0)")
    sql = "SELECT * FROM inventory_boxes"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY box_code"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def product_totals(conn, *, status="in_stock") -> list[dict]:
    """Tổng tồn + số thùng theo từng product (cho trang danh mục kho)."""
    rows = conn.execute(
        "SELECT product_code, COUNT(*) AS box_count, COALESCE(SUM(quantity),0) AS total "
        "FROM inventory_boxes WHERE status = ? GROUP BY product_code ORDER BY product_code",
        (status,),
    ).fetchall()
    return [dict(r) for r in rows]


def product_summary(conn) -> list[dict]:
    """Tồn/xuất theo product cho dashboard. Thùng vô hiệu KHÔNG tính vào tồn (chỉ đếm riêng)."""
    rows = conn.execute(
        "SELECT product_code, "
        "COALESCE(SUM(CASE WHEN status='in_stock' AND (disabled IS NULL OR disabled=0) THEN quantity ELSE 0 END),0) AS in_stock_total, "
        "SUM(CASE WHEN status='in_stock' AND (disabled IS NULL OR disabled=0) THEN 1 ELSE 0 END) AS in_stock_count, "
        "SUM(CASE WHEN status='allocated' THEN 1 ELSE 0 END) AS allocated_count, "
        "SUM(CASE WHEN status='shipped'   THEN 1 ELSE 0 END) AS shipped_count, "
        "SUM(CASE WHEN disabled=1 THEN 1 ELSE 0 END) AS disabled_count, "
        "COUNT(*) AS total_count "
        "FROM inventory_boxes GROUP BY product_code ORDER BY product_code"
    ).fetchall()
    return [dict(r) for r in rows]


def get_box(conn, box_id) -> dict | None:
    row = conn.execute("SELECT * FROM inventory_boxes WHERE id = ?", (box_id,)).fetchone()
    return dict(row) if row else None


def allocate_boxes(conn, box_ids, order_thread_id, *, by=None) -> list[int]:
    """Xuất kho: gán thùng in_stock cho đơn. Trả id các thùng thực sự xuất.

    Bỏ qua thùng đã allocated/shipped (tránh xuất trùng). Nguyên tử.
    """
    if not box_ids:
        return []
    now = _now()
    allocated: list[int] = []
    with transaction(conn):
        for bid in box_ids:
            row = conn.execute("SELECT status, disabled FROM inventory_boxes WHERE id = ?", (bid,)).fetchone()
            if not row or row[0] != "in_stock" or row[1]:
                continue  # bỏ thùng đã xuất/giao hoặc bị vô hiệu
            conn.execute(
                "UPDATE inventory_boxes SET status='allocated', order_thread_id=?, "
                "allocated_at=?, allocated_by=? WHERE id = ?",
                (order_thread_id, now, by or "", bid),
            )
            allocated.append(bid)
    return allocated


def release_boxes(conn, box_ids) -> list[int]:
    """Thu hồi thùng đã xuất về in_stock (huỷ xuất). Trả id đã thu hồi. Nguyên tử."""
    if not box_ids:
        return []
    released: list[int] = []
    with transaction(conn):
        for bid in box_ids:
            cur = conn.execute(
                "UPDATE inventory_boxes SET status='in_stock', order_thread_id=NULL, "
                "allocated_at=NULL, allocated_by=NULL WHERE id = ? AND status='allocated'",
                (bid,),
            )
            if cur.rowcount:
                released.append(bid)
    return released


def update_box(conn, box_id, *, quantity=None, note=None) -> bool:
    sets, params = [], []
    if quantity is not None:
        sets.append("quantity = ?"); params.append(float(quantity))
    if note is not None:
        sets.append("note = ?"); params.append(note)
    if not sets:
        return False
    params.append(box_id)
    with transaction(conn):
        conn.execute(f"UPDATE inventory_boxes SET {', '.join(sets)} WHERE id = ?", params)
    return True


def set_disabled(conn, box_id, disabled: bool) -> bool:
    """Vô hiệu / kích hoạt lại 1 thùng. Nếu vô hiệu thùng đang xuất → thu về in_stock."""
    with transaction(conn):
        if disabled:
            conn.execute(
                "UPDATE inventory_boxes SET disabled=1, status='in_stock', order_thread_id=NULL, "
                "allocated_at=NULL, allocated_by=NULL WHERE id = ?",
                (box_id,),
            )
        else:
            conn.execute("UPDATE inventory_boxes SET disabled=0 WHERE id = ?", (box_id,))
    return True


def delete_box(conn, box_id) -> bool:
    with transaction(conn):
        conn.execute("DELETE FROM inventory_boxes WHERE id = ?", (box_id,))
    return True
