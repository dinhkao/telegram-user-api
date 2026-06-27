from __future__ import annotations

import logging
import os

log = logging.getLogger("mirror_channel")
ORDER_MIRROR_CHANNEL = int(os.getenv("ORDER_MIRROR_CHANNEL", "-1004377987052"))


async def sync_order_to_mirror(client, conn, thread_id: int) -> None:
    try:
        from order_db import get_order_by_thread_id, _save_order
        from order_html import build_order_main_message_html
        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            return
        html = build_order_main_message_html(order, thread_id)
        if not html:
            return
        old_msg_id = order.get("mirror_message_id")
        if old_msg_id:
            try:
                await client.delete_messages(ORDER_MIRROR_CHANNEL, old_msg_id)
            except Exception:
                pass
        sent = await client.send_message(ORDER_MIRROR_CHANNEL, html, parse_mode="html", link_preview=False)
        order["mirror_message_id"] = sent.id
        _save_order(conn, thread_id, order)
        log.info("Mirror synced: thread=%d old_msg=%s new_msg=%d", thread_id, old_msg_id, sent.id)
    except Exception as e:
        log.warning("Mirror sync failed for thread=%d: %s", thread_id, e)
