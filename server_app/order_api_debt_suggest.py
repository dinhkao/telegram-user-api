"""Gợi ý 'Bỏ theo dõi nợ' đơn cũ — GET /api/order/{thread_id}/debt-suggest.

Sau khi bước 'Nhận tiền / Gửi toa cho khách' của một đơn xong, webapp gọi
endpoint này: trả về các đơn KHÁC của CÙNG KHÁCH còn bị theo dõi nợ (😡, đúng
tiêu chí chip lọc Nợ dashboard: chưa có thanh toán, chưa 😑, tạo từ 01/07/2026)
và TẠO TRƯỚC đơn hiện tại → client hiện popup gợi ý bật 😑 hàng loạt.
Nói chuyện với: order_db (app.db), server_app.customer_feed (_order_total_num).
"""
from __future__ import annotations

import json

from aiohttp import web

from order_db import _get_connection, get_order_by_thread_id
from server_app.customer_feed import _order_total_num

# Đơn cũ hơn mốc này chưa qua flow thanh toán — khớp filter Nợ (orders_api.py)
_TRACK_MIN_CREATED = "2026-07-01"


async def api_debt_suggest_handler(request: web.Request):
    try:
        thread_id = int(request.match_info["thread_id"])
    except (KeyError, ValueError):
        return web.json_response({"ok": False, "error": "Bad thread_id"}, status=400)
    conn = _get_connection()
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return web.json_response({"ok": False, "error": "Order not found"}, status=404)
    key = order.get("khach_hang_id") or order.get("khID")
    if not key:
        return web.json_response({"ok": True, "orders": []})
    key = str(key)
    created = str(order.get("created") or "")
    rows = conn.execute(
        "SELECT o.thread_id, o.json FROM orders o WHERE ("
        " CAST(json_extract(o.json,'$.khach_hang_id') AS TEXT) = ?"
        " OR CAST(json_extract(o.json,'$.khID') AS TEXT) = ? )"
        " AND o.deleted_at IS NULL AND o.thread_id IS NOT NULL AND o.thread_id != ?",
        (key, key, thread_id),
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        try:
            data = json.loads(r["json"])
        except (TypeError, ValueError):
            continue
        if data.get("payments"):
            continue
        if data.get("bo_theo_doi_no") in (1, True, "1", "true"):
            continue
        c = str(data.get("created") or "")
        # Chỉ đơn TRƯỚC đơn hiện tại, trong phạm vi chip lọc Nợ
        if c < _TRACK_MIN_CREATED or (created and c >= created):
            continue
        out.append({
            "thread_id": r["thread_id"],
            "created": c,
            "text": (data.get("text") or "").strip()[:80],
            "total": _order_total_num(data),
        })
    out.sort(key=lambda o: o["created"])
    return web.json_response({"ok": True, "orders": out})
