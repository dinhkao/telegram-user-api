from __future__ import annotations
import time
from typing import Optional

from .schema import _PRODUCTS_CACHE_TTL, _invalidate_products_cache, _products_cache


_COLS = "code, name, cost_price, note, kv_id, kv_full_name, kv_synced_at, created_at, updated_at"


def _row(r) -> dict:
    return {"code": r[0], "name": r[1], "cost_price": r[2] or 0, "note": r[3],
            "kv_id": r[4], "kv_full_name": r[5], "kv_synced_at": r[6],
            "created_at": r[7], "updated_at": r[8]}


def get_product(conn, code: str) -> Optional[dict]:
    row = conn.execute(
        f"SELECT {_COLS} FROM products WHERE code = ?", (code.upper().strip(),),
    ).fetchone()
    return _row(row) if row else None


def get_all_products(conn, *, _use_cache: bool = True) -> list[dict]:
    now = time.monotonic()
    if _use_cache and _products_cache["data"] is not None and (now - _products_cache["ts"]) < _PRODUCTS_CACHE_TTL:
        return _products_cache["data"]
    result = [_row(r) for r in conn.execute(f"SELECT {_COLS} FROM products ORDER BY code").fetchall()]
    _products_cache["data"], _products_cache["ts"] = result, now
    return result


def upsert_product(conn, code: str, name: str = None, cost_price: int = None, note: str = None) -> bool:
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
        if not updates:
            return True
        updates.append("updated_at = ?"); params.extend([now, code])
        conn.execute(f"UPDATE products SET {', '.join(updates)} WHERE code = ?", params)
    else:
        conn.execute("INSERT INTO products (code, name, cost_price, note, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)", (code, name or "", cost_price or 0, note or "", now, now))
    conn.commit(); _invalidate_products_cache(); return True


def sync_kiotviet_products(conn, kv_products: list[dict]) -> int:
    """Nhập/ghi đè liên kết KiotViet vào products theo mã (code).
    kv_products: [{code, id, full_name}]. Sản phẩm chưa có → tạo (name từ KiotViet).
    Đã có → gắn kv_id/kv_full_name/kv_synced_at (KHÔNG đụng cost_price/note local).
    Trả số dòng xử lý. Đây là điểm liên kết code↔KiotViet (mã trùng = valid trên KV)."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    count = 0
    for p in kv_products:
        code = (p.get("code") or "").upper().strip()
        kv_id = p.get("id")
        if not code or not kv_id:
            continue
        full = p.get("full_name") or p.get("fullName") or p.get("name") or ""
        existing = get_product(conn, code)
        if existing:
            conn.execute(
                "UPDATE products SET kv_id = ?, kv_full_name = ?, kv_synced_at = ?, "
                "name = COALESCE(NULLIF(name, ''), ?), updated_at = ? WHERE code = ?",
                (kv_id, full, now, full, now, code),
            )
        else:
            conn.execute(
                "INSERT INTO products (code, name, cost_price, note, kv_id, kv_full_name, kv_synced_at, created_at, updated_at) "
                "VALUES (?, ?, 0, '', ?, ?, ?, ?, ?)",
                (code, full, kv_id, full, now, now, now),
            )
        count += 1
    conn.commit(); _invalidate_products_cache()
    return count


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
