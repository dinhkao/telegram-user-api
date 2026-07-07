"""CRUD công thức (product_recipes) + tính nhu cầu nguyên liệu. IO + transaction.
Nối: utils.db. Consume kho thực hiện ở inventory_store.fifo_consume.
"""
from __future__ import annotations

from utils.db import transaction


def _code(x) -> str:
    return str(x or "").strip().upper()


def list_recipe(conn, product_code) -> list[dict]:
    """Các nguyên liệu của 1 sản phẩm: [{id, ingredient_code, ratio, optional}]."""
    rows = conn.execute(
        "SELECT id, ingredient_code, ratio, COALESCE(optional,0) AS optional "
        "FROM product_recipes WHERE product_code = ? ORDER BY optional, ingredient_code",
        (_code(product_code),),
    ).fetchall()
    return [dict(r) for r in rows]


def set_recipe_line(conn, product_code, ingredient_code, ratio, optional: bool = False) -> dict | None:
    """Thêm/sửa 1 nguyên liệu (upsert theo cặp). ratio > 0. optional=True → không bắt
    buộc khi sản xuất. Không cho tự làm nguyên liệu."""
    pc, ic = _code(product_code), _code(ingredient_code)
    try:
        r = float(ratio)
    except (TypeError, ValueError):
        return None
    if not pc or not ic or ic == pc or r <= 0:
        return None
    opt = 1 if optional else 0
    with transaction(conn):
        conn.execute(
            "INSERT INTO product_recipes (product_code, ingredient_code, ratio, optional) VALUES (?,?,?,?) "
            "ON CONFLICT(product_code, ingredient_code) DO UPDATE SET ratio = excluded.ratio, optional = excluded.optional",
            (pc, ic, r, opt),
        )
    row = conn.execute(
        "SELECT id, ingredient_code, ratio, COALESCE(optional,0) AS optional FROM product_recipes WHERE product_code = ? AND ingredient_code = ?",
        (pc, ic),
    ).fetchone()
    return dict(row) if row else None


def delete_recipe_line(conn, line_id) -> bool:
    with transaction(conn):
        conn.execute("DELETE FROM product_recipes WHERE id = ?", (int(line_id),))
    return True


def recipe_needs(conn, product_code, produced_qty) -> list[dict]:
    """Nhu cầu nguyên liệu khi sản xuất produced_qty cây thành phẩm:
    [{code, amount}] với amount = ratio × produced_qty. Rỗng nếu chưa có công thức."""
    q = float(produced_qty or 0)
    if q <= 0:
        return []
    return [
        {"code": r["ingredient_code"], "amount": round(r["ratio"] * q, 3), "optional": bool(r.get("optional"))}
        for r in list_recipe(conn, product_code)
    ]
