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


def add_boxes(conn, product_code, quantities, *, source_thread_id=None, by=None, note=None, mfg_date=None) -> list[dict]:
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
                "(product_code, box_code, quantity, status, source_thread_id, note, mfg_date, created_at, created_by) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (code, box_code, float(q), "in_stock", source_thread_id, note or "", mfg_date or None, now, by or ""),
            )
            created.append({
                "id": cur.lastrowid, "product_code": code, "box_code": box_code,
                "quantity": float(q), "status": "in_stock", "mfg_date": mfg_date or None,
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
        where.append("b.product_code = ?"); params.append(str(product_code).strip().upper())
    if status:
        where.append("b.status = ?"); params.append(status)
    if source_thread_id is not None:
        where.append("b.source_thread_id = ?"); params.append(source_thread_id)
    if order_thread_id is not None:
        where.append("b.order_thread_id = ?"); params.append(order_thread_id)
    if active_only:
        where.append("(b.disabled IS NULL OR b.disabled = 0)")
    sql = (
        "SELECT b.*, "
        "COALESCE((SELECT SUM(a.quantity) FROM box_allocations a WHERE a.box_id=b.id),0) AS allocated "
        "FROM inventory_boxes b"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY b.box_code"
    out = []
    for r in conn.execute(sql, params).fetchall():
        d = dict(r)
        d["remaining"] = float(d.get("quantity") or 0) - float(d.get("allocated") or 0)
        out.append(d)
    return out


def product_totals(conn, *, status="in_stock") -> list[dict]:
    """Tổng tồn + số thùng theo từng product (cho trang danh mục kho)."""
    rows = conn.execute(
        "SELECT product_code, COUNT(*) AS box_count, COALESCE(SUM(quantity),0) AS total "
        "FROM inventory_boxes WHERE status = ? GROUP BY product_code ORDER BY product_code",
        (status,),
    ).fetchall()
    return [dict(r) for r in rows]


def product_summary(conn) -> list[dict]:
    """Tồn/xuất theo product cho dashboard. Tồn = tổng CÒN LẠI (remaining) của thùng
    còn hiệu lực; đã xuất = số thùng có phần xuất; vô hiệu đếm riêng (không tính tồn)."""
    agg: dict = {}
    for b in list_boxes(conn):
        code = b["product_code"]
        g = agg.setdefault(code, {
            "product_code": code, "in_stock_total": 0.0, "in_stock_count": 0,
            "allocated_count": 0, "shipped_count": 0, "disabled_count": 0, "total_count": 0,
        })
        g["total_count"] += 1
        if b.get("disabled"):
            g["disabled_count"] += 1
        elif b["remaining"] > 0:
            g["in_stock_total"] += b["remaining"]
            g["in_stock_count"] += 1
        if (b.get("allocated") or 0) > 0:
            g["allocated_count"] += 1
    return [agg[k] for k in sorted(agg)]


def get_box(conn, box_id) -> dict | None:
    row = conn.execute("SELECT * FROM inventory_boxes WHERE id = ?", (box_id,)).fetchone()
    return dict(row) if row else None


def update_box(conn, box_id, *, quantity=None, note=None, mfg_date=None) -> bool:
    sets, params = [], []
    if quantity is not None:
        sets.append("quantity = ?"); params.append(float(quantity))
    if note is not None:
        sets.append("note = ?"); params.append(note)
    if mfg_date is not None:
        sets.append("mfg_date = ?"); params.append(mfg_date or None)
    if not sets:
        return False
    params.append(box_id)
    with transaction(conn):
        conn.execute(f"UPDATE inventory_boxes SET {', '.join(sets)} WHERE id = ?", params)
    return True


def set_disabled(conn, box_id, disabled: bool, reason: str | None = None) -> bool:
    """Vô hiệu / kích hoạt lại 1 thùng (chỉ đặt cờ + lý do). Không đụng status/đơn —
    caller phải bảo đảm thùng KHÔNG đang phân bổ đơn trước khi vô hiệu. Kích hoạt lại
    xoá lý do."""
    with transaction(conn):
        if disabled:
            conn.execute(
                "UPDATE inventory_boxes SET disabled=1, disabled_reason=? WHERE id = ?",
                (reason or "", box_id),
            )
        else:
            conn.execute(
                "UPDATE inventory_boxes SET disabled=0, disabled_reason=NULL WHERE id = ?", (box_id,)
            )
    return True


def delete_box(conn, box_id) -> bool:
    with transaction(conn):
        conn.execute("DELETE FROM inventory_boxes WHERE id = ?", (box_id,))
    return True
