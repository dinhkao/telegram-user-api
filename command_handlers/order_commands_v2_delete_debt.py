from __future__ import annotations

import asyncio
import html as _html
import logging
import os

from order_db import _save_order, get_customer_by_key, get_order_by_thread_id
from kiotviet import get_customer_debt_kv

from .order_commands_v2_utils import refresh_main_msg

log = logging.getLogger("order_commands_v2")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))


def _get_order_total_value(order: dict) -> float:
    items_total = 0
    for it in (order.get("invoice") or []):
        try:
            items_total += float(it.get("price") or 0) * float(it.get("sl") or 0)
        except (TypeError, ValueError):
            pass
    pvc = float(order.get("pvc") or 0)
    vat = float(order.get("vat") or 0)
    discount = float(order.get("discount") or 0)
    return items_total + pvc + vat - discount


async def update_debt_command(client, msg, db_conn, thread_id):
    """Handle "update debt" command: fetch live KiotViet debt, adjust by
    pending order total when an invoice already exists, save + reply."""
    order = get_order_by_thread_id(db_conn, thread_id)
    if not order:
        return "❌ Không tìm thấy đơn hàng"
    kh_id_fb = order.get("khach_hang_id") or order.get("khID")
    if not kh_id_fb:
        return "❌ Đơn hàng chưa có khách hàng"
    customer = get_customer_by_key(db_conn, str(kh_id_fb))
    kv_id = customer.get("kh_id") if customer else None
    if not kv_id:
        return "❌ Khách hàng chưa liên kết KiotViet"
    try:
        kv_debt = get_customer_debt_kv(kv_id).get("debt")
    except Exception as e:
        return f"⚠️ {e}"
    if kv_debt is None:
        return "⚠️ Không lấy được công nợ KiotViet"
    display_debt = kv_debt
    if order.get("kiotvietInvoiceID"):
        display_debt = kv_debt - _get_order_total_value(order)
    order["khDebt"] = display_debt
    _save_order(db_conn, thread_id, order)
    if not order.get("kiotvietInvoiceID") and order.get("channel_id") and order.get("message_id"):
        await refresh_main_msg(client, db_conn, thread_id, order["channel_id"], order["message_id"])
    return f"Cập nhật nợ khách hàng -> {display_debt:,.0f}đ"


async def update_debt_and_notify(client, db_conn, thread_id, order, kh_id_fb, old_debt):
    """Update khDebt after invoice delete (with retry) + notify customer topic.
    Returns list of debt_lines for final status message."""
    debt_lines = []
    if not kh_id_fb:
        return debt_lines
    try:
        customer = get_customer_by_key(db_conn, str(kh_id_fb))
        kv_id = customer.get("kh_id") if customer else None
        if not kv_id:
            return debt_lines
        new_debt = None
        for attempt in range(1, 6):
            try:
                new_debt = get_customer_debt_kv(kv_id).get("debt", 0)
            except Exception:
                pass
            if old_debt is None or new_debt is None or new_debt != old_debt or attempt == 5:
                break
            await asyncio.sleep(1.2 * attempt)
        if new_debt is not None:
            order["khDebt"] = new_debt
            _save_order(db_conn, thread_id, order)
            if old_debt is not None:
                delta = new_debt - old_debt
                debt_lines.append(f"💰 Nợ: {old_debt:,}đ → {new_debt:,}đ ({delta:+,}đ)")
            else:
                debt_lines.append(f"💰 Nợ: {new_debt:,}đ")
            await _notify_customer_topic(client, thread_id, order, kh_id_fb, old_debt, new_debt, delta)
    except Exception as e:
        log.warning("Debt update after invoice delete failed: %s", e)
    return debt_lines


async def _notify_customer_topic(client, thread_id, order, kh_id_fb, old_debt, new_debt, delta):
    order_group_str = str(ORDER_GROUP_ID)
    internal_id = order_group_str[4:] if order_group_str.startswith("-100") else str(abs(ORDER_GROUP_ID))
    order_topic_url = f"https://t.me/c/{internal_id}/{thread_id}"
    title = _html.escape(str(order.get("text") or f"Đơn hàng #{thread_id}"))
    note = f'🗑️ Xóa hoá đơn của <a href="{order_topic_url}">{title}</a>'
    if old_debt is not None:
        note += f"\nNợ cũ: {old_debt:,}đ\nNợ mới: {new_debt:,}đ ({delta:+,}đ)"
    try:
        await client.send_message(ORDER_GROUP_ID, note, parse_mode="html", reply_to=int(kh_id_fb))
    except Exception as e2:
        log.warning("Customer topic notify failed: %s", e2)