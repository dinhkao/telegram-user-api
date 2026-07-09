"""Tra các ĐƠN có chứa 1 sản phẩm trong invoice — cho trang chi tiết SP.

Khớp theo DANH TÍNH SP: `sp_id` (đơn từ 2026-07, backfill toàn bộ) HOẶC mã `sp`
∈ {mã hiện hành + MỌI mã cũ theo product_code_history} — nên đổi mã xong tra cứu
KHÔNG đứt, đơn lịch sử vẫn hiện. Quét json bằng json_each, nguồn mảng $.invoice
fallback $.invoice_items. GROUP BY thread_id, phân trang. Dùng bởi: inventory_routes.
"""
from __future__ import annotations

# Nguồn mảng SP: ưu tiên $.invoice, fallback $.invoice_items (đơn cũ), rồi '[]'.
_ARR = "coalesce(json_extract(o.json, '$.invoice'), json_extract(o.json, '$.invoice_items'), '[]')"


def _match_clause(conn, code: str) -> tuple[str, list]:
    """(mảnh WHERE, params) khớp 1 item với SP (nhận cả mã cũ trong URL)."""
    from product_store import old_codes_of, resolve_code
    prod = resolve_code(conn, code)
    if not prod:
        return "upper(json_extract(je.value, '$.sp')) = ?", [str(code or "").upper().strip()]
    codes = sorted({str(prod["code"]).upper(), *old_codes_of(conn, prod["id"])})
    ph = ",".join("?" * len(codes))
    return (
        f"(json_extract(je.value, '$.sp_id') = ? OR upper(json_extract(je.value, '$.sp')) IN ({ph}))",
        [prod["id"], *codes],
    )


def count_orders_containing_product(conn, code: str) -> int:
    """Tổng số ĐƠN (distinct) có SP này."""
    code = (code or "").upper().strip()
    if not code:
        return 0
    frag, params = _match_clause(conn, code)
    row = conn.execute(
        f"""
        SELECT COUNT(DISTINCT o.thread_id)
        FROM orders o, json_each({_ARR}) je
        WHERE o.deleted_at IS NULL AND {frag}
        """,
        params,
    ).fetchone()
    return int(row[0] or 0)


def orders_containing_product(conn, code: str, limit: int = 20, offset: int = 0) -> list[dict]:
    """[{thread_id, text (dòng đầu), sl (tổng), price, created}] các đơn có SP này,
    mới→cũ, mỗi đơn 1 dòng. Phân trang qua limit/offset."""
    code = (code or "").upper().strip()
    if not code:
        return []
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    frag, params = _match_clause(conn, code)
    rows = conn.execute(
        f"""
        SELECT o.thread_id,
               json_extract(o.json, '$.text')                    AS text,
               SUM(CAST(json_extract(je.value, '$.sl') AS INTEGER)) AS sl,
               MAX(CAST(json_extract(je.value, '$.price') AS INTEGER)) AS price,
               json_extract(o.json, '$.created')                 AS created,
               o.updated_at                                       AS uat
        FROM orders o, json_each({_ARR}) je
        WHERE o.deleted_at IS NULL AND {frag}
        GROUP BY o.thread_id
        ORDER BY uat DESC
        LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        text = (r[1] or "").strip().split("\n")[0][:70]
        out.append({"thread_id": r[0], "text": text, "sl": r[2], "price": r[3], "created": r[4]})
    return out
