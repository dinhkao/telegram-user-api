"""GỢI Ý khi gõ ô tìm dashboard Đơn — GET /api/orders/suggest?q= → khách + sản phẩm.

Đọc `customers` (order_store.customers.search_customers) + danh mục SP
(product_store.get_all_products, cache sẵn). Chọn 1 gợi ý thì client đặt ô tìm =
tên khách / MÃ SP rồi dùng lại FTS đơn như cũ (orders_db.search_orders_fts — mã SP
tự mở rộng alias mã cũ). Xếp hạng thuần ở `rank_*` (tests/test_order_suggest.py).
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from order_db import _get_connection
from order_store.customers import search_customers
from product_store.queries import get_all_products
from vn import vn_normalize

_LIMIT = 6


def _match_rank(q: str, text: str) -> int | None:
    """0 = trùng hẳn · 1 = bắt đầu bằng · 2 = 1 TỪ bắt đầu bằng · 3 = chứa (liền, hoặc
    đủ MỌI từ của q ở bất kỳ đâu — "keo dua" khớp "keo dau phong dua") · None = không khớp."""
    if not text:
        return None
    if q not in text:
        return 3 if all(t in text for t in q.split()) else None
    if text == q:
        return 0
    if text.startswith(q):
        return 1
    if any(w.startswith(q) for w in text.split()):
        return 2
    return 3


def rank_customers(q: str, rows: list[dict], limit: int = _LIMIT) -> list[dict]:
    """rows: [{key, name, ...}] ĐÃ sắp khách mua gần nhất trước (khớp cả mẫu nhận
    diện). Khớp ngay TÊN được đẩy lên; hoà thì giữ thứ tự gần-đây (sort ổn định)."""
    def rk(r: dict) -> int:
        m = _match_rank(q, vn_normalize(r.get("name") or ""))
        return 4 if m is None else m
    return sorted(rows, key=rk)[:limit]


def rank_products(q: str, products: list[dict], limit: int = _LIMIT) -> list[dict]:
    """Đầu MÃ ưu tiên nhất, rồi đầu TÊN, rồi chứa ở giữa; bỏ SP tắt bán (can_sell=0 — nguyên liệu/bao bì
    không bao giờ nằm trong đơn)."""
    scored = []
    for p in products:
        if not p.get("can_sell", True):
            continue
        rc = _match_rank(q, vn_normalize(p.get("code") or ""))
        rn = _match_rank(q, vn_normalize(p.get("name") or ""))
        if rc is None and rn is None:
            continue
        # mã trùng/đầu mã (0,1) > đầu tên/đầu 1 từ của tên (2,3) > chứa trong mã (4) > chứa trong tên (5)
        sc = {0: 0, 1: 1, 2: 4, 3: 4}.get(rc, 9)
        sn = {0: 2, 1: 2, 2: 3, 3: 5}.get(rn, 9)
        score = min(sc, sn)
        scored.append((score, len(p.get("code") or ""), p))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [p for _, _, p in scored[:limit]]


async def orders_suggest_handler(request: web.Request):
    q = vn_normalize(request.query.get("q", "").strip())
    if not q:
        return web.json_response({"ok": True, "customers": [], "products": []})

    def _run():
        conn = _get_connection()
        try:
            custs, _ = search_customers(conn, q, limit=60, sort="recent")
            rows = [{"key": c.get("_firebase_key", ""),
                     "name": c.get("name") or c.get("ten") or c.get("_firebase_key", "")} for c in custs]
            prods = rank_products(q, get_all_products(conn))
            return rank_customers(q, rows), prods
        finally:
            conn.close()

    custs, prods = await asyncio.to_thread(_run)
    return web.json_response({
        "ok": True,
        "customers": custs,
        "products": [{"code": p["code"], "name": p.get("name") or ""} for p in prods],
    })
