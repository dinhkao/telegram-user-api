"""Tra các ĐƠN có chứa 1 mã sản phẩm (sp) trong invoice — cho trang chi tiết SP.

Quét cột json của bảng orders bằng json_each trên mảng $.invoice (SQLite native).
coalesce '[]' cho đơn chưa có invoice. Dùng bởi: server_app/inventory_routes.
"""
from __future__ import annotations


def orders_containing_product(conn, code: str, limit: int = 100) -> list[dict]:
    """[{thread_id, text (dòng đầu), sl, price, created}] các đơn có mã `code`,
    mới→cũ, đã gộp trùng theo đơn. code so khớp không phân biệt hoa/thường."""
    code = (code or "").upper().strip()
    if not code:
        return []
    rows = conn.execute(
        """
        SELECT o.thread_id,
               json_extract(o.json, '$.text')      AS text,
               json_extract(je.value, '$.sl')       AS sl,
               json_extract(je.value, '$.price')    AS price,
               json_extract(o.json, '$.created')    AS created,
               o.updated_at
        FROM orders o,
             json_each(coalesce(json_extract(o.json, '$.invoice'), '[]')) je
        WHERE o.deleted_at IS NULL
          AND upper(json_extract(je.value, '$.sp')) = ?
        ORDER BY o.updated_at DESC
        LIMIT ?
        """,
        (code, max(1, min(500, int(limit)))),
    ).fetchall()
    out: list[dict] = []
    seen: set = set()
    for r in rows:
        tid = r[0]
        if tid in seen:
            continue
        seen.add(tid)
        text = (r[1] or "").strip().split("\n")[0][:70]
        out.append({"thread_id": tid, "text": text, "sl": r[2], "price": r[3], "created": r[4]})
    return out
