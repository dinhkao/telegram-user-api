from __future__ import annotations

import asyncio
import html as _html
import logging
import os

from order_db import _save_order, get_customer_by_key
from kiotviet import get_customer_debt_kv

log = logging.getLogger("order_commands_v2")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))


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
        await client.send_message(ORDER_GROUP_ID, note, parse_mode="html", message_thread_id=int(kh_id_fb))
    except Exception as e2:
        log.warning("Customer topic notify failed: %s", e2)