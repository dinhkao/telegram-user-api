from __future__ import annotations

import json
import logging
import os

from aiohttp import web

from order_db import _get_connection, detect_customer_free_text, get_customer_by_key, get_customer_price_list, get_order_by_thread_id, parse_invoice_free_text, _save_order


def _customer_extra(conn, cust_key) -> dict:
    """Nợ (snapshot) + tên bảng giá đang gán của khách (cho preview)."""
    cust = get_customer_by_key(conn, cust_key) or {}
    pl_name = None
    plid = cust.get("price_list")
    if plid:
        r = conn.execute("SELECT value FROM kv_store WHERE path = 'bang_gia_moi'").fetchone()
        if r and r["value"]:
            book = json.loads(r["value"]).get(str(plid), {})
            pl_name = (book.get("name") or "").strip() or f"BG {plid}"
    if cust.get("personal_price_list"):
        pl_name = f"{pl_name} + riêng" if pl_name else "Bảng giá riêng"
    return {
        "debt": cust.get("debt"),
        "debt_updated_at": cust.get("debt_updated_at"),
        "price_list_name": pl_name,
    }
from product_db import freeze_invoice_cost_prices

from server_app import state
from server_app.config import ORDER_GROUP_ID
from server_app.order_api_common import refresh_order_bg
from server_app.tasks import spawn_tracked
from server_app.telegram_helpers import tg_send_message

log = logging.getLogger("server")


async def order_preview_handler(request: web.Request):
    """Xem trước kết quả parse text đơn (khách + sản phẩm + tổng) — KHÔNG tạo/lưu/
    gửi Telegram. Dùng cho preview tức thời ở tab 'Nhanh' trang tạo đơn."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    text = (body.get("text") or "").strip()
    manual_key = (body.get("customer_key") or "").strip() or None
    if not text and not manual_key:
        return web.json_response({"ok": True, "customer": None, "candidates": [], "invoice": [], "total": 0})
    conn = _get_connection()

    # Khách: ưu tiên khách người dùng CHỌN tay; nếu không thì tự nhận diện từ text
    detection = None
    if manual_key:
        kh_id = manual_key
        cust = get_customer_by_key(conn, kh_id) or {}
        name = cust.get("name") or cust.get("ten") or None
        assigned_out = {"id": kh_id, "name": name, "score": 100, "manual": True}
    else:
        detection = detect_customer_free_text(conn, text)
        a = detection["autoAssign"] if detection.get("autoAssign") else None
        kh_id = a["customerID"] if a else None
        assigned_out = {"id": a["customerID"], "name": a["customerName"], "score": a["score"], "manual": False} if a else None

    invoice = parse_invoice_free_text(conn, text, kh_id) if text else []
    if invoice and kh_id and get_customer_price_list(conn, kh_id):
        invoice = parse_invoice_free_text(conn, text, kh_id)
    invoice = invoice or []
    total = sum((it.get("sl", 0) or 0) * (it.get("price", 0) or 0) for it in invoice)

    customer_out = {**assigned_out, **_customer_extra(conn, kh_id)} if assigned_out else None
    candidates = [] if (manual_key or assigned_out) else [
        {"id": m["customerID"], "name": m["customerName"], "score": m["score"]}
        for m in ((detection or {}).get("matches") or [])[:3]
    ]
    return web.json_response({
        "ok": True,
        "customer": customer_out,
        "candidates": candidates,
        "invoice": [{
            "sp": it.get("sp"), "sl": it.get("sl", 0), "price": it.get("price", 0),
            "sub": (it.get("sl", 0) or 0) * (it.get("price", 0) or 0),
        } for it in invoice],
        "total": total,
    })


async def auto_parse_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    thread_id, text = body.get("thread_id"), (body.get("text") or "").strip()
    if not thread_id or not text:
        return web.json_response({"ok": False, "error": "Missing thread_id or text"}, status=400)
    conn = _get_connection()
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return web.json_response({"ok": False, "error": "Order not found in SQLite"}, status=404)
    kh_id_fb = order.get("khach_hang_id") or order.get("khID")
    detection = detect_customer_free_text(conn, text)
    assigned_cust = detection["autoAssign"] if detection["autoAssign"] else None
    if assigned_cust:
        order.update({"khach_hang_id": assigned_cust["customerID"], "customer_name": assigned_cust["customerName"]})
        kh_id_fb = assigned_cust["customerID"]
    invoice = parse_invoice_free_text(conn, text, kh_id_fb)
    if invoice and assigned_cust and get_customer_price_list(conn, assigned_cust["customerID"]):
        invoice = parse_invoice_free_text(conn, text, assigned_cust["customerID"])
    if invoice:
        order["invoice"] = freeze_invoice_cost_prices(conn, invoice)
    _save_order(conn, thread_id, order)
    log.info("auto-parse: thread=%d items=%d assigned=%s", thread_id, len(invoice) if invoice else 0, assigned_cust["customerName"] if assigned_cust else "none")
    if state._client is not None:
        lines = []
        if invoice:
            lines.append(f"🤖 <b>Auto-detect:</b> đã tìm thấy {len(invoice)} sản phẩm\n")
            total = 0
            for item in invoice:
                sub = item.get("sl", 0) * item.get("price", 0)
                total += sub
                lines.append(f"• <b>{item.get('sp', '?')}</b> x{item.get('sl', 0)} @ {item.get('price', 0):,}đ = <b>{sub:,}đ</b>")
            lines.append(f"\n💰 <b>Tổng cộng: {total:,}đ</b>")
        if assigned_cust:
            if lines:
                lines.append("")
            lines += [f"👤 <b>Đã gán:</b> {assigned_cust['customerName']} ({assigned_cust['score']}%)", f"🎯 Mẫu: \"{assigned_cust['bestMatchedPattern']}\""]
        elif detection["matches"]:
            if lines:
                lines.append("")
            lines.append("🔍 <b>Khách hàng có thể:</b>")
            for i, m in enumerate(detection["matches"][:3]):
                lines.append(f"  {i+1}. {m['customerName']} ({m['score']}%) — <code>add khach hang {m['customerID']}</code>")
        if lines:
            spawn_tracked("auto_parse.notification", tg_send_message(ORDER_GROUP_ID, "\n".join(lines), reply_to=thread_id, parse_mode="html"), {"thread_id": thread_id})
    row = conn.execute("SELECT channel_id, message_id FROM orders WHERE thread_id = ?", (thread_id,)).fetchone()
    if row and row["channel_id"] and row["message_id"]:
        spawn_tracked("order.refresh", refresh_order_bg(conn, thread_id, row["channel_id"], row["message_id"]), {"thread_id": thread_id, "channel_id": row["channel_id"], "message_id": row["message_id"]})
    return web.json_response({"ok": True, "parsed": len(invoice), "auto_assigned": detection["autoAssign"]["customerID"] if detection.get("autoAssign") else None})
