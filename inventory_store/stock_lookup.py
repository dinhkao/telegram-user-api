"""Tồn kho HIỆN TẠI của 1 vài mã SP (nhận cả mã cũ) — tra nhanh cho ô tìm dashboard Đơn.
Cùng luật tồn với `queries.product_summary`: Σ còn lại (quantity − Σ allocations) của
thùng CÒN HIỆU LỰC và còn hàng. Nối: inventory_boxes, box_allocations, product_store."""
from __future__ import annotations


def stock_of(conn, product: dict) -> dict:
    """{stock, boxes} của 1 SP (dict product hiện hành: cần id + code)."""
    row = conn.execute(
        "SELECT COALESCE(SUM(rem), 0), COUNT(*) FROM ("
        " SELECT b.quantity - COALESCE((SELECT SUM(a.quantity) FROM box_allocations a"
        "  WHERE a.box_id = b.id), 0) AS rem"
        " FROM inventory_boxes b"
        " WHERE (b.product_id = ? OR (b.product_id IS NULL AND UPPER(b.product_code) = ?))"
        "  AND COALESCE(b.disabled, 0) = 0"
        ") WHERE rem > 0",
        (product["id"], str(product["code"]).upper()),
    ).fetchone()
    stock = float(row[0] or 0)
    return {"stock": int(stock) if stock == int(stock) else round(stock, 3), "boxes": int(row[1] or 0)}


def stock_by_code(conn, code: str) -> dict | None:
    """Mã (hiện hành hoặc cũ) → {code, name, unit, stock, boxes, display?} | None.
    `display` = quy đổi theo vai 👁 HIỂN THỊ của SP (vd 90 cây = 3 Thùng) nếu có."""
    from product_store import resolve_code
    from product_store.units import list_units, unit_role
    prod = resolve_code(conn, code)
    if not prod:
        return None
    out = {"code": prod["code"], "name": prod.get("name") or "", "unit": prod.get("unit") or "cây",
           **stock_of(conn, prod)}
    try:
        role = unit_role(prod, list_units(conn, int(prod["id"])), "display")
    except Exception:  # noqa: BLE001 — chưa có bảng product_units (DB cũ/test)
        role = None
    if role and role.get("id") and role.get("factor"):
        out["display"] = {"name": role["name"], "qty": round(out["stock"] / role["factor"], 1)}
    return out
