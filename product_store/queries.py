from __future__ import annotations
import time
from typing import Optional

from .schema import _PRODUCTS_CACHE_TTL, _invalidate_products_cache, _products_cache


_COLS = "id, code, name, cost_price, note, kv_id, kv_full_name, kv_synced_at, created_at, updated_at, unit, is_material"
_FIELDS = tuple(c.strip() for c in _COLS.split(","))


def _row(r) -> dict:
    d = dict(zip(_FIELDS, r))
    d["cost_price"] = d["cost_price"] or 0
    d["unit"] = d["unit"] or "cây"
    d["is_material"] = bool(d["is_material"])
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


def set_material(conn, code: str, flag: bool) -> bool:
    """Đánh dấu SP là nguyên liệu (dùng làm thành phần đóng gói). Chỉ update nếu SP có."""
    code = code.upper().strip()
    if not code or not get_product(conn, code):
        return False
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    conn.execute("UPDATE products SET is_material = ?, updated_at = ? WHERE code = ?", (1 if flag else 0, now, code))
    conn.commit(); _invalidate_products_cache(); return True


def upsert_product(conn, code: str, name: str = None, cost_price: int = None, note: str = None, unit: str = None, is_material: bool = None) -> bool:
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
        if is_material is not None:
            updates.append("is_material = ?"); params.append(1 if is_material else 0)
        if not updates:
            return True
        updates.append("updated_at = ?"); params.extend([now, code])
        conn.execute(f"UPDATE products SET {', '.join(updates)} WHERE code = ?", params)
    else:
        conn.execute("INSERT INTO products (code, name, cost_price, note, unit, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (code, name or "", cost_price or 0, note or "", (unit or "cây").strip() or "cây", now, now))
    conn.commit(); _invalidate_products_cache(); return True


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
