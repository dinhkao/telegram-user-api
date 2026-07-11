from __future__ import annotations
import time
from typing import Optional

from .schema import _PRODUCTS_CACHE_TTL, _invalidate_products_cache, _products_cache


_COLS = "id, code, name, cost_price, note, kv_id, kv_full_name, kv_synced_at, created_at, updated_at, unit, is_material, prod_mam, prod_luong, can_produce_directly, min_stock, self_container"
_FIELDS = tuple(c.strip() for c in _COLS.split(","))


def _row(r) -> dict:
    d = dict(zip(_FIELDS, r))
    d["cost_price"] = d["cost_price"] or 0
    d["unit"] = d["unit"] or "cây"
    d["is_material"] = bool(d["is_material"])
    d["can_produce_directly"] = d.get("can_produce_directly") != 0   # SX trực tiếp được (mặc định True)
    d["min_stock"] = float(d.get("min_stock") or 0)   # tồn kho tối thiểu
    d["self_container"] = bool(d.get("self_container"))   # SP bản thân là 1 thùng
    return d


def get_product(conn, code: str) -> Optional[dict]:
    row = conn.execute(
        f"SELECT {_COLS} FROM products WHERE code = ?", (code.upper().strip(),),
    ).fetchone()
    return _row(row) if row else None


def get_product_by_id(conn, product_id) -> Optional[dict]:
    """Tra theo danh tính BẤT BIẾN (products.id) — dùng cho mọi liên kết nội bộ."""
    if product_id is None:
        return None
    row = conn.execute(
        f"SELECT {_COLS} FROM products WHERE id = ?", (int(product_id),),
    ).fetchone()
    return _row(row) if row else None


def get_all_products(conn, *, _use_cache: bool = True) -> list[dict]:
    now = time.monotonic()
    if _use_cache and _products_cache["data"] is not None and (now - _products_cache["ts"]) < _PRODUCTS_CACHE_TTL:
        return _products_cache["data"]
    result = [_row(r) for r in conn.execute(f"SELECT {_COLS} FROM products ORDER BY code").fetchall()]
    _products_cache["data"], _products_cache["ts"] = result, now
    return result


def upsert_product(conn, code: str, name: str = None, cost_price: int = None, note: str = None, unit: str = None, prod_mam: float = None, prod_luong: float = None, can_produce_directly: bool = None, min_stock: float = None, self_container: bool = None) -> bool:
    code = code.upper().strip()
    if not code:
        return False
    existing = get_product(conn, code)
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    if existing:
        updates, params = [], []
        if name is not None:
            updates.append("name = ?"); params.append(name)
        if cost_price is not None:
            updates.append("cost_price = ?"); params.append(cost_price)
        if note is not None:
            updates.append("note = ?"); params.append(note)
        if unit is not None:
            updates.append("unit = ?"); params.append(unit.strip() or "cây")
        if prod_mam is not None:
            updates.append("prod_mam = ?"); params.append(float(prod_mam) if prod_mam != "" else None)
        if prod_luong is not None:
            updates.append("prod_luong = ?"); params.append(float(prod_luong) if prod_luong != "" else None)
        if can_produce_directly is not None:
            updates.append("can_produce_directly = ?"); params.append(1 if can_produce_directly else 0)
        if min_stock is not None:
            updates.append("min_stock = ?"); params.append(float(min_stock) if min_stock != "" else 0)
        if self_container is not None:
            updates.append("self_container = ?"); params.append(1 if self_container else 0)
        if not updates:
            return True
        updates.append("updated_at = ?"); params.extend([now, code])
        conn.execute(f"UPDATE products SET {', '.join(updates)} WHERE code = ?", params)
    else:
        cur = conn.execute(
            "INSERT INTO products (code, name, cost_price, note, unit, prod_mam, prod_luong, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (code, name or "", cost_price or 0, note or "", (unit or "cây").strip() or "cây",
             prod_mam, prod_luong, now, now))
        _adopt_orphan_snapshots(conn, cur.lastrowid, code)
    conn.commit(); _invalidate_products_cache(); return True


def _adopt_orphan_snapshots(conn, product_id, code: str) -> None:
    """SP MỚI vào danh mục 'nhận nuôi' các row mồ côi trùng mã — thùng/công thức/
    phiếu SX/lịch sử giá từng tạo bằng mã gõ tự do (product_id NULL) nay có danh
    tính. Nhờ đó trang chi tiết SP sửa/đổi mã được ngay. Bảng thiếu (DB test) bỏ qua."""
    import sqlite3 as _sq
    for sql in (
        "UPDATE inventory_boxes SET product_id = ? WHERE product_id IS NULL AND UPPER(TRIM(product_code)) = ?",
        "UPDATE product_recipes SET product_id = ? WHERE product_id IS NULL AND UPPER(TRIM(product_code)) = ?",
        "UPDATE product_recipes SET ingredient_id = ? WHERE ingredient_id IS NULL AND UPPER(TRIM(ingredient_code)) = ?",
        "UPDATE production_slips SET product_id = ? WHERE product_id IS NULL AND UPPER(TRIM(COALESCE(sp_name,''))) = ?",
        "UPDATE production_report_rows SET product_id = ? WHERE product_id IS NULL AND UPPER(TRIM(COALESCE(product_code,''))) = ?",
        "UPDATE price_history SET product_id = ? WHERE product_id IS NULL AND UPPER(TRIM(sp)) = ?",
    ):
        try:
            conn.execute(sql, (product_id, code))
        except _sq.OperationalError:
            pass


def set_kiotviet_link(conn, code: str, kv_id: int, full_name: str = "") -> Optional[dict]:
    """Liên kết 1 mã SP local với 1 sản phẩm KiotViet (từng cái). KHÔNG đụng
    cost_price/note; điền name nếu đang trống. Trả product đã cập nhật, None nếu
    mã không tồn tại."""
    code = code.upper().strip()
    if not code or not kv_id or not get_product(conn, code):
        return None
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    conn.execute(
        "UPDATE products SET kv_id = ?, kv_full_name = ?, kv_synced_at = ?, "
        "name = COALESCE(NULLIF(name, ''), ?), updated_at = ? WHERE code = ?",
        (int(kv_id), full_name or "", now, full_name or "", now, code),
    )
    conn.commit(); _invalidate_products_cache()
    return get_product(conn, code)


def clear_kiotviet_link(conn, code: str) -> Optional[dict]:
    """Bỏ liên kết KiotViet của 1 mã SP."""
    code = code.upper().strip()
    if not get_product(conn, code):
        return None
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    conn.execute(
        "UPDATE products SET kv_id = NULL, kv_full_name = NULL, kv_synced_at = NULL, updated_at = ? WHERE code = ?",
        (now, code),
    )
    conn.commit(); _invalidate_products_cache()
    return get_product(conn, code)


def delete_product(conn, code: str) -> bool:
    conn.execute("DELETE FROM products WHERE code = ?", (code.upper().strip(),))
    conn.commit(); _invalidate_products_cache(); return True


def bulk_update_cost_prices(conn, updates: list[dict]) -> int:
    count = 0
    for item in updates:
        code = item.get("code", "").upper().strip()
        if code and item.get("cost_price") is not None and upsert_product(conn, code, cost_price=item.get("cost_price")):
            count += 1
    if count:
        _invalidate_products_cache()
    return count
