"""Đổi MÃ sản phẩm (admin) — cascade mọi dữ liệu VẬN HÀNH trong app.db cùng 1
transaction: products (PK), product_recipes (cả cột SP lẫn nguyên liệu),
inventory_boxes, bảng giá CHUNG (kv_store 'bang_gia_moi') + bảng giá RIÊNG từng
khách (customers.$.personal_price_list), production_slips.sp_name,
production_report_rows.product_code. ĐƠN HÀNG CŨ giữ mã cũ (bản ghi lịch sử,
tên đã snapshot — không đụng). Nối: utils.db, .schema (cache).
"""
from __future__ import annotations

import json
import sqlite3
import time

from utils.db import transaction

from .schema import _invalidate_products_cache


def _code(x) -> str:
    return str(x or "").strip().upper()


def rename_product_code(conn, old_code, new_code) -> tuple[dict | None, str | None]:
    """Trả (product sau khi đổi, None) hoặc (None, lý do lỗi)."""
    old, new = _code(old_code), _code(new_code)
    if not old or not new:
        return None, "Thiếu mã"
    if old == new:
        return None, "Mã mới trùng mã cũ"
    if conn.execute("SELECT 1 FROM products WHERE code = ?", (new,)).fetchone():
        return None, f"Mã {new} đã tồn tại trong danh mục"
    if not conn.execute("SELECT 1 FROM products WHERE code = ?", (old,)).fetchone():
        return None, f"Mã {old} không có trong danh mục"
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    try:
        with transaction(conn):
            conn.execute("UPDATE products SET code = ?, updated_at = ? WHERE code = ?", (new, now, old))
            # Công thức: SP này là thành phẩm + SP này là nguyên liệu của SP khác
            conn.execute("UPDATE product_recipes SET product_code = ? WHERE product_code = ?", (new, old))
            conn.execute("UPDATE product_recipes SET ingredient_code = ? WHERE ingredient_code = ?", (new, old))
            conn.execute("UPDATE inventory_boxes SET product_code = ? WHERE product_code = ?", (new, old))
            # Phiếu SX (bảng có thể chưa tạo trên DB test → bỏ qua nếu thiếu)
            for sql in (
                "UPDATE production_slips SET sp_name = ? WHERE UPPER(COALESCE(sp_name,'')) = ?",
                "UPDATE production_report_rows SET product_code = ? WHERE UPPER(COALESCE(product_code,'')) = ?",
            ):
                try:
                    conn.execute(sql, (new, old))
                except sqlite3.OperationalError:
                    pass
            # Bảng giá CHUNG: kv_store['bang_gia_moi'] = {id: {price_list: {CODE: giá}}}
            row = conn.execute("SELECT value FROM kv_store WHERE path = 'bang_gia_moi'").fetchone()
            if row and row["value"]:
                data = json.loads(row["value"])
                changed = False
                for pl in data.values():
                    prices = (pl or {}).get("price_list") or {}
                    if old in prices:
                        prices[new] = prices.pop(old)
                        changed = True
                if changed:
                    conn.execute("UPDATE kv_store SET value = ? WHERE path = 'bang_gia_moi'",
                                 (json.dumps(data, ensure_ascii=False),))
            # Bảng giá RIÊNG từng khách (JSON blob customers)
            for r in conn.execute(
                "SELECT firebase_key, json FROM customers WHERE deleted_at IS NULL "
                "AND json_extract(json, '$.personal_price_list') IS NOT NULL"
            ).fetchall():
                cust = json.loads(r["json"])
                personal = cust.get("personal_price_list") or {}
                if old in personal:
                    personal[new] = personal.pop(old)
                    cust["personal_price_list"] = personal
                    conn.execute("UPDATE customers SET json = ? WHERE firebase_key = ?",
                                 (json.dumps(cust, ensure_ascii=False), r["firebase_key"]))
    except sqlite3.Error as e:
        return None, f"Lỗi DB khi đổi mã: {e}"
    _invalidate_products_cache()
    from .queries import get_product
    return get_product(conn, new), None
