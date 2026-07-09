from __future__ import annotations

import asyncio
import logging

from order_db import get_order_by_thread_id

from .config import CHANNEL_DON_HANG_MOI

log = logging.getLogger("channel_handler")
_debt_fetch_in_progress: set[int] = set()


async def render_channel_post(client, conn, thread_id: int, message_id: int, order=None):
    try:
        from order_html import build_order_main_message_html
        order = order or get_order_by_thread_id(conn, thread_id)
        if not order:
            return
        html = build_order_main_message_html(order, thread_id)
        if not html:
            return
        await client.edit_message(CHANNEL_DON_HANG_MOI, message_id, html, parse_mode="html")
        log.info("Channel post rendered: thread=%d msg=%d", thread_id, message_id)
        kh_id_fb = order.get("khach_hang_id") or order.get("khID")
        if kh_id_fb and not order.get("khDebt") and thread_id not in _debt_fetch_in_progress:
            _debt_fetch_in_progress.add(thread_id)
            client.loop.create_task(fetch_debt_and_rerender(client, thread_id, message_id, str(kh_id_fb)))
    except Exception as e:
        log.warning("Failed to render channel post thread=%d: %s", thread_id, e)


async def fetch_debt_and_rerender(client, thread_id: int, message_id: int, kh_id_fb: str):
    try:
        from kiotviet import get_customer_debt_kv
        from order_db import _get_connection, _update_order_json_field, get_customer_by_key, get_order_by_thread_id
        conn = _get_connection()
        try:
            cust = get_customer_by_key(conn, kh_id_fb)
        finally:
            conn.close()
        if not cust or not cust.get("kh_id"):
            return
        det = await asyncio.get_running_loop().run_in_executor(None, get_customer_debt_kv, cust["kh_id"])
        debt_val = det.get("debt")
        if debt_val is None:
            return
        conn2 = _get_connection()
        try:
            _update_order_json_field(conn2, thread_id, "$.khDebt", debt_val)
            _update_order_json_field(conn2, thread_id, "$.invoice_debt_snapshot", det.get("debt", 0))
            from order_db import update_customer_debt
            update_customer_debt(conn2, kh_id_fb, debt_val)
        finally:
            conn2.close()
        # Nợ vừa về blob → báo webapp (OrderDetail đang mở hiện "Nợ trước —" tới khi có event)
        from server_app.realtime import emit_customer_changed, emit_order_changed
        emit_order_changed(thread_id)
        emit_customer_changed(str(kh_id_fb))
        conn3 = _get_connection()
        try:
            updated_order = get_order_by_thread_id(conn3, thread_id)
        finally:
            conn3.close()
        if updated_order:
            from order_html import build_order_main_message_html
            html = build_order_main_message_html(updated_order, thread_id)
            if html:
                await client.edit_message(CHANNEL_DON_HANG_MOI, message_id, html, parse_mode="html")
                log.info("Channel post updated with debt: thread=%d debt=%d", thread_id, debt_val)
    except Exception as e:
        log.warning("Failed to fetch debt + rerender thread=%d: %s", thread_id, e)
    finally:
        _debt_fetch_in_progress.discard(thread_id)
