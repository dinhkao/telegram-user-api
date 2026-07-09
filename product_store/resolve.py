"""Resolve mã SP → product hiện hành. Luật: mã trong DANH MỤC HIỆN TẠI thắng;
mã cũ tra product_code_history (entry mới nhất thắng). Kèm alias map cho parser
và ghi nhật ký đổi mã. Nối: .queries, product_code_history (schema)."""
from __future__ import annotations

import time

from .queries import get_all_products, get_product, get_product_by_id


def resolve_code(conn, code) -> dict | None:
    """Mã (hiện hành HOẶC cũ) → product dict hiện hành. None nếu không nhận ra."""
    c = str(code or "").strip().upper()
    if not c:
        return None
    p = get_product(conn, c)
    if p:
        return p
    row = conn.execute(
        "SELECT product_id FROM product_code_history WHERE UPPER(old_code) = ? "
        "ORDER BY id DESC LIMIT 1",
        (c,),
    ).fetchone()
    return get_product_by_id(conn, row[0]) if row else None


def resolve_code_to_id(conn, code) -> int | None:
    p = resolve_code(conn, code)
    return int(p["id"]) if p else None


def code_alias_map(conn) -> dict[str, int]:
    """{mã_cũ: product_id} cho parser nhận mã cũ — CHỈ mã cũ không trùng mã hiện
    hành nào (mã tái dùng → SP hiện tại thắng, alias bỏ). 1 mã qua tay nhiều SP →
    entry mới nhất thắng (duyệt theo id tăng, sau đè trước)."""
    current = {p["code"].upper() for p in get_all_products(conn)}
    out: dict[str, int] = {}
    for r in conn.execute(
        "SELECT old_code, product_id FROM product_code_history ORDER BY id"
    ).fetchall():
        oc = str(r[0] or "").strip().upper()
        if oc and oc not in current:
            out[oc] = int(r[1])
    return out


def old_codes_of(conn, product_id) -> list[str]:
    """Mọi mã cũ của 1 SP (mở rộng search / tra đơn lịch sử)."""
    rows = conn.execute(
        "SELECT DISTINCT UPPER(old_code) FROM product_code_history WHERE product_id = ?",
        (int(product_id),),
    ).fetchall()
    return [r[0] for r in rows if r[0]]


def record_code_change(conn, product_id, old_code, new_code, by: str = "") -> None:
    """Ghi 1 dòng nhật ký đổi mã (caller tự bọc transaction cùng UPDATE code)."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    conn.execute(
        "INSERT INTO product_code_history (product_id, old_code, new_code, changed_at, changed_by) "
        "VALUES (?, ?, ?, ?, ?)",
        (int(product_id), str(old_code).strip().upper(), str(new_code).strip().upper(), now, by or ""),
    )
