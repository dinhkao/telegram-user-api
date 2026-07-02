"""POST /api/order/create — tạo đơn mới từ web app (DB-only, không tạo topic Telegram).

Đơn web có thread_id ÂM (−epoch giây, không đụng thread_id Telegram dương) và
firebase_key `web_<epoch>`. Text tự do → detect khách (customer_detect) + parse
invoice (free_text) — cùng pipeline auto-parse của Telegram. Người tạo lấy từ
request["web_user"] (web_auth). Connects to: order_store, product_db.
Đăng ký ở server_app/app_factory.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime

from aiohttp import web

from order_db import (
    _create_order,
    _get_connection,
    detect_customer_free_text,
    get_order_by_thread_id,
    parse_invoice_free_text,
    transaction,
)
from product_db import freeze_invoice_cost_prices


def _build_and_insert(text: str, creator: str, customer_key: str | None) -> dict:
    conn = _get_connection()
    now = int(time.time())
    thread_id = -now
    with transaction(conn):
        while get_order_by_thread_id(conn, thread_id) is not None:
            thread_id -= 1
        kh_id, customer_name = customer_key, ""
        if not kh_id and text:
            detection = detect_customer_free_text(conn, text)
            assigned = detection.get("autoAssign") if isinstance(detection, dict) else None
            if assigned:
                kh_id, customer_name = assigned["customerID"], assigned["customerName"]
        invoice = parse_invoice_free_text(conn, text, kh_id) if text else []
        if invoice:
            invoice = freeze_invoice_cost_prices(conn, invoice)
        data = {
            "text": text,
            "text_raw": text,
            "created": datetime.now().isoformat(),
            "thread_id": thread_id,
            # key theo thread_id (đã uniquify) — không phải `now`, tránh 2 đơn cùng
            # giây trùng PRIMARY KEY rồi bị INSERT OR IGNORE nuốt im lặng
            "firebase_key": f"web_{-thread_id}",
            "channel_id": 0,
            "message_id": 0,
            "flow_version": "web",
            "customer_name": customer_name,
            "khach_hang_id": kh_id,
            "invoice": invoice,
            "payments": [],
            "task_status": {},
            "nguoi_tao_HD": [creator],
        }
        if not _create_order(conn, data["firebase_key"], thread_id, 0, 0, data):
            raise RuntimeError("insert thất bại")
        if kh_id:
            from order_db import touch_customer_last_order
            touch_customer_last_order(conn, kh_id)
        # _create_order dùng INSERT OR IGNORE và trả True cả khi bị bỏ qua — xác nhận
        if get_order_by_thread_id(conn, thread_id) is None:
            raise RuntimeError("insert bị bỏ qua (trùng key) — thử lại")
    return {"thread_id": thread_id, "key": data["firebase_key"], "customer_name": customer_name, "khach_hang_id": kh_id, "invoice_count": len(invoice)}


async def order_create_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "body phải là JSON"}, status=400)
    text = str(body.get("text") or "").strip()
    if not text:
        return web.json_response({"ok": False, "error": "thiếu text đơn hàng"}, status=400)
    from server_app.order_api_common import apply_web_actor
    apply_web_actor(request, body, key="user")
    creator = str(body.get("user") or "web")
    customer_key = str(body.get("customer_key") or "").strip() or None
    try:
        result = await asyncio.to_thread(_build_and_insert, text, creator, customer_key)
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)
    from server_app.realtime import emit_orders_changed
    emit_orders_changed()  # đơn web mới → dashboard refetch ngay
    from server_app.fcm import notify_bg
    notify_bg("🆕 Đơn mới (web)", text.strip()[:120], {"thread_id": str(result.get("thread_id"))})
    return web.json_response({"ok": True, **result})
