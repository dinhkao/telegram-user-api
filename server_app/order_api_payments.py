from __future__ import annotations

import logging

from aiohttp import web

from order_db import _get_connection, get_order_by_thread_id, get_customer_price_list

from server_app.order_api_common import apply_web_actor
from server_app.telegram_helpers import tg_send_message

log = logging.getLogger("server")


async def _payment_handler(request: web.Request, method: str):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    apply_web_actor(request, body)
    thread_id, amount, user_id = body.get("thread_id"), body.get("amount"), body.get("user_id")
    if not thread_id or not amount:
        return web.json_response({"ok": False, "error": "Missing thread_id or amount"}, status=400)
    try:
        from order_commands_v3 import _process_payment_core
        result = await _process_payment_core(int(thread_id), int(amount), user_id, method)
    except Exception as e:
        log.error("Payment API error: %s", e, exc_info=True)
        return web.json_response({"ok": False, "error": str(e)}, status=500)
    return web.json_response({"ok": True, "thread_id": result["thread_id"], "amount": result["amount"], "method": result["method"], "method_label": result["method_label"], "kv_code": result["kv_code"], "old_debt": result["old_debt"], "new_debt": result["new_debt"]}) if result["success"] else web.json_response({"ok": False, "error": result["error"]}, status=400)


async def payment_tm_handler(request: web.Request):
    return await _payment_handler(request, "Cash")


async def payment_ck_handler(request: web.Request):
    return await _payment_handler(request, "Transfer")


async def order_totals_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    thread_id = body.get("thread_id")
    if not thread_id:
        return web.json_response({"ok": False, "error": "Missing thread_id"}, status=400)
    try:
        conn = _get_connection()
        order = get_order_by_thread_id(conn, int(thread_id))
        if not order:
            return web.json_response({"ok": False, "error": "Order not found"}, status=404)
        invoice = order.get("invoice") or order.get("san_pham") or []
        total = sum(int(item.get("price", 0)) * int(item.get("sl", 1)) for item in invoice)
        discount, pvc, vat = order.get("discount", 0), order.get("pvc", 0), order.get("vat", 0)
        pre_debt_total = total - discount + pvc + vat
        return web.json_response({"ok": True, "order": {"pre_debt_total": pre_debt_total, "total_payable": pre_debt_total, "total": total, "discount": discount, "pvc": pvc, "vat": vat}})
    except Exception as e:
        log.error("Totals API error: %s", e, exc_info=True)
        return web.json_response({"ok": False, "error": str(e)}, status=500)
    finally:
        try:
            conn.close()
        except Exception:
            pass


async def api_customer_price_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    customer_id, product = body.get("customer_id"), (body.get("product") or "").upper().strip()
    if not customer_id or not product:
        return web.json_response({"ok": False, "error": "Missing customer_id or product"}, status=400)
    conn = _get_connection()
    from order_store.search import get_customer_price_source
    price, source, list_name = get_customer_price_source(conn, str(customer_id), product)
    return web.json_response({"ok": True, "price": price, "product": product, "source": source, "list_name": list_name})
