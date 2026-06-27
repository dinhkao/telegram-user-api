from __future__ import annotations
import json
import time

_customer_patterns_cache: dict = {"data": None, "ts": 0}
_CUSTOMER_PATTERNS_TTL = 60


def _invalidate_customer_patterns_cache():
    _customer_patterns_cache["data"] = None
    _customer_patterns_cache["ts"] = 0


def search_products(conn, code_or_name: str, limit: int = 15) -> list[dict]:
    pattern = f"%{code_or_name}%"
    try:
        cur = conn.execute("SELECT value FROM kv_store WHERE path LIKE ? ORDER BY path LIMIT ?", (f"%product%{pattern}%", limit))
        results = []
        for (json_text,) in cur:
            try:
                d = json.loads(json_text)
                if isinstance(d, dict):
                    results.append(d)
            except json.JSONDecodeError:
                continue
        if results:
            return results
    except Exception:
        pass
    try:
        from kiotviet import search_products_kv
        results = search_products_kv(code_or_name, limit)
        if results:
            return results
    except Exception:
        pass
    return []


def get_customer_price_list(conn, kh_id: str | int) -> dict[str, int]:
    row = conn.execute("SELECT json FROM customers WHERE firebase_key = ? AND deleted_at IS NULL", (str(kh_id),)).fetchone()
    if not row:
        return {}
    cust = json.loads(row["json"])
    price_list = {}
    price_list_id = cust.get("price_list")
    if price_list_id:
        row = conn.execute("SELECT value FROM kv_store WHERE path = 'bang_gia_moi'").fetchone()
        if row and row["value"]:
            price_list = json.loads(row["value"]).get(str(price_list_id), {}).get("price_list", {})
    personal = cust.get("personal_price_list")
    if personal and isinstance(personal, dict):
        price_list = {**price_list, **personal}
    return price_list
