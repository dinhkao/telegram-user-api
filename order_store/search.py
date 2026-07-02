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


def get_customer_price_source(conn, kh_id, product) -> tuple[int, str | None, str | None]:
    """Trả (giá, nguồn, tên_bảng_giá) cho 1 SP theo khách.

    nguồn: 'personal' (bảng giá riêng của khách, đè lên) | 'shared' (bảng giá
    chung khách đang gán) | None (không có). Dùng để ghi rõ giá lấy từ bảng nào."""
    product = str(product).upper().strip()
    row = conn.execute("SELECT json FROM customers WHERE firebase_key = ? AND deleted_at IS NULL", (str(kh_id),)).fetchone()
    if not row:
        return 0, None, None
    cust = json.loads(row["json"])
    personal = cust.get("personal_price_list") or {}
    if isinstance(personal, dict) and product in personal:
        return int(personal[product] or 0), "personal", "Bảng giá riêng"
    plid = cust.get("price_list")
    if plid:
        r = conn.execute("SELECT value FROM kv_store WHERE path = 'bang_gia_moi'").fetchone()
        if r and r["value"]:
            book = json.loads(r["value"]).get(str(plid), {})
            pl = book.get("price_list", {}) or {}
            if product in pl:
                name = (book.get("name") or "").strip() or f"BG {plid}"
                return int(pl[product] or 0), "shared", name
    return 0, None, None
