"""Tra các ĐƠN có chứa 1 mã sản phẩm (sp) trong invoice — cho trang chi tiết SP.

Quét cột json bảng orders bằng json_each. Nguồn mảng = $.invoice HOẶC $.invoice_items
(đơn cũ) — coalesce nên không sót. GROUP BY thread_id → mỗi đơn 1 dòng (gộp nếu mã
xuất hiện nhiều lần). Phân trang (limit/offset) để lazy-load. Dùng bởi: inventory_routes.
"""
from __future__ import annotations

# Nguồn mảng SP: ưu tiên $.invoice, fallback $.invoice_items (đơn cũ), rồi '[]'.
_ARR = "coalesce(json_extract(o.json, '$.invoice'), json_extract(o.json, '$.invoice_items'), '[]')"


def count_orders_containing_product(conn, code: str) -> int:
    """Tổng số ĐƠN (distinct) có mã `code`."""
    code = (code or "").upper().strip()
    if not code:
        return 0
    row = conn.execute(
        f"""
        SELECT COUNT(DISTINCT o.thread_id)
        FROM orders o, json_each({_ARR}) je
        WHERE o.deleted_at IS NULL
          AND upper(json_extract(je.value, '$.sp')) = ?
        """,
        (code,),
    ).fetchone()
    return int(row[0] or 0)


def orders_containing_product(conn, code: str, limit: int = 20, offset: int = 0) -> list[dict]:
    """[{thread_id, text (dòng đầu), sl (tổng), price, created}] các đơn có mã `code`,
    mới→cũ, mỗi đơn 1 dòng. Phân trang qua limit/offset."""
    code = (code or "").upper().strip()
    if not code:
        return []
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    rows = conn.execute(
        f"""
        SELECT o.thread_id,
               json_extract(o.json, '$.text')                    AS text,
               SUM(CAST(json_extract(je.value, '$.sl') AS INTEGER)) AS sl,
               MAX(CAST(json_extract(je.value, '$.price') AS INTEGER)) AS price,
               json_extract(o.json, '$.created')                 AS created,
               o.updated_at                                       AS uat
        FROM orders o, json_each({_ARR}) je
        WHERE o.deleted_at IS NULL
          AND upper(json_extract(je.value, '$.sp')) = ?
        GROUP BY o.thread_id
        ORDER BY uat DESC
        LIMIT ? OFFSET ?
        """,
        (code, limit, offset),
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        text = (r[1] or "").strip().split("\n")[0][:70]
        out.append({"thread_id": r[0], "text": text, "sl": r[2], "price": r[3], "created": r[4]})
    return out
