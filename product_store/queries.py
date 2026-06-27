from __future__ import annotations
import time
from typing import Optional

from .schema import _PRODUCTS_CACHE_TTL, _invalidate_products_cache, _products_cache


def get_product(conn, code: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT code, name, cost_price, note, created_at, updated_at FROM products WHERE code = ?",
        (code.upper().strip(),),
    ).fetchone()
    if not row:
        return None
    return {"code": row[0], "name": row[1], "cost_price": row[2] or 0, "note": row[3], "created_at": row[4], "updated_at": row[5]}


def get_all_products(conn, *, _use_cache: bool = True) -> list[dict]:
    now = time.monotonic()
    if _use_cache and _products_cache["data"] is not None and (now - _products_cache["ts"]) < _PRODUCTS_CACHE_TTL:
        return _products_cache["data"]
    result = [{"code": r[0], "name": r[1], "cost_price": r[2] or 0, "note": r[3], "created_at": r[4], "updated_at": r[5]} for r in conn.execute("SELECT code, name, cost_price, note, created_at, updated_at FROM products ORDER BY code").fetchall()]
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
