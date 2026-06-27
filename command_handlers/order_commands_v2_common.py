from __future__ import annotations

from order_db import get_order_by_thread_id
from order_store.orders import _call_final_telegram


def extract_thread_id(msg) -> int | None:
    reply = getattr(msg, "reply_to", None)
    if reply:
        thread_id = getattr(reply, "reply_to_top_id", None) or getattr(reply, "reply_to_msg_id", None)
        if thread_id and not getattr(reply, "forum_topic", False):
            return getattr(reply, "reply_to_top_id", None)
        if thread_id:
            return thread_id
    thread_id = getattr(msg, "reply_to_top_id", None)
    if thread_id:
        return thread_id
    raw = getattr(msg, "_raw", None) or getattr(msg, "original_update", None)
    if raw and getattr(raw, "reply_to", None):
        return getattr(raw.reply_to, "reply_to_top_id", None)
    return None


def call_final(endpoint: str, body: dict, timeout: int = 10) -> dict | None:
    return _call_final_telegram(endpoint, body, timeout)


async def refresh_main_msg(client, conn, thread_id, channel_id, message_id):
    try:
        from order_html import build_order_main_message_html

        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            return
        await client.edit_message(entity=channel_id, message=message_id, text=build_order_main_message_html(order, thread_id), parse_mode="html", link_preview=False)
    except Exception:
        pass
