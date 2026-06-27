from __future__ import annotations

import logging
import os

from order_db import _call_final_telegram

log = logging.getLogger("order_commands_v3")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))

TASK_MIRROR_FIELDS = {
    "soan_hang": "soan",
    "giao_hang": "giao",
    "nop_tien": "nop",
    "nhan_tien": "nhan",
}


def _extract_thread_id(msg) -> int | None:
    thread_id = None
    if msg.reply_to:
        thread_id = (
            getattr(msg.reply_to, "reply_to_top_id", None)
            or getattr(msg.reply_to, "reply_to_msg_id", None)
        )
        if thread_id and not getattr(msg.reply_to, "forum_topic", False):
            thread_id = getattr(msg.reply_to, "reply_to_top_id", None)
    if not thread_id:
        thread_id = getattr(msg, "reply_to_top_id", None)
    if not thread_id:
        raw = getattr(msg, "_raw", None) or getattr(msg, "original_update", None)
        if raw:
            r = getattr(raw, "reply_to", None)
            if r:
                thread_id = getattr(r, "reply_to_top_id", None)
    return thread_id


def _call_final(endpoint: str, body: dict, timeout: int = 10) -> dict | None:
    return _call_final_telegram(endpoint, body, timeout)


async def _resolve_name(client, user_id: int) -> str:
    try:
        entity = await client.get_entity(user_id)
        first = getattr(entity, "first_name", "") or ""
        last = getattr(entity, "last_name", "") or ""
        if first:
            return f"{first} {last}".strip()
        username = getattr(entity, "username", "") or ""
        if username:
            return f"@{username}"
        return str(user_id)
    except Exception:
        return str(user_id)


def _sync_task_mirror(order: dict) -> None:
    task_status = order.get("task_status")
    if not task_status or not isinstance(task_status, dict):
        return
    for task_type, field in TASK_MIRROR_FIELDS.items():
        entry = task_status.get(task_type)
        if entry and isinstance(entry, dict):
            order[field] = bool(entry.get("done") or entry.get("skip"))


def _clean_text_chat(order: dict) -> None:
    text_chat = (order.get("text_chat") or "").strip()
    if not text_chat:
        return
    cleaned = " ".join(
        w for w in text_chat.split()
        if w not in ("cs", "cg", "cnt", "cnhan")
    )
    if cleaned != text_chat:
        order["text_chat"] = cleaned
