"""CRUD công thức (product_recipes) + tính nhu cầu nguyên liệu. IO + transaction.
Nối: utils.db. Trừ kho thực hiện ở inventory_store.allocate_picks(kind='production').
"""
from __future__ import annotations

from utils.db import transaction


def _code(x) -> str:
    return str(x or "").strip().upper()


def list_recipe(conn, product_code) -> list[dict]:
    """Các nguyên liệu của 1 sản phẩm: [{id, ingredient_code, ratio}]."""
    rows = conn.execute(
        "SELECT id, ingredient_code, ratio "
        "FROM product_recipes WHERE product_code = ? ORDER BY ingredient_code",
        (_code(product_code),),
    ).fetchall()
    return [dict(r) for r in rows]


def set_recipe_line(conn, product_code, ingredient_code, ratio) -> dict | None:
    """Thêm/sửa 1 nguyên liệu (upsert theo cặp). ratio > 0. Không cho tự làm
    nguyên liệu. Nhu cầu NL do LOẠI PHIẾU quyết định (chỉ đóng gói mới bắt buộc)."""
    pc, ic = _code(product_code), _code(ingredient_code)
    try:
        r = float(ratio)
    except (TypeError, ValueError):
        return None
    if not pc or not ic or ic == pc or r <= 0:
        return None
    with transaction(conn):
        conn.execute(
            "INSERT INTO product_recipes (product_code, ingredient_code, ratio) VALUES (?,?,?) "
            "ON CONFLICT(product_code, ingredient_code) DO UPDATE SET ratio = excluded.ratio",
            (pc, ic, r),
        )
    row = conn.execute(
        "SELECT id, ingredient_code, ratio FROM product_recipes WHERE product_code = ? AND ingredient_code = ?",
        (pc, ic),
    ).fetchone()
    return dict(row) if row else None


def delete_recipe_line(conn, line_id) -> bool:
    with transaction(conn):
        conn.execute("DELETE FROM product_recipes WHERE id = ?", (int(line_id),))
    return True


def recipe_needs(conn, product_code, produced_qty) -> list[dict]:
    """Nhu cầu nguyên liệu khi làm produced_qty cây thành phẩm:
    [{code, amount}] với amount = ratio × produced_qty. Rỗng nếu chưa có công thức.
    Chỉ phiếu ĐÓNG GÓI mới bắt buộc đáp ứng đủ (validate ở inventory_routes)."""
    q = float(produced_qty or 0)
    if q <= 0:
        return []
    return [
        {"code": r["ingredient_code"], "amount": round(r["ratio"] * q, 3)}
        for r in list_recipe(conn, product_code)
    ]
