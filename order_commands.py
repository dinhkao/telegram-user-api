"""order_commands.py — V2 task command handlers via Telethon.

Listens for task commands (soan, giao, ban, nop, nhan, xuat hd, etc.)
in the order group chat. Writes task_status to SQLite, replies via
Telethon, then fire-and-forgets a refresh to final_telegram's updateView.
"""
from __future__ import annotations
import http.client
import json
import logging
import os
import re
import time
from telethon import events
from telethon.tl.types import MessageService

from order_db import (
    _get_connection,
    get_order_by_thread_id,
    set_task_status,
    clear_task_status,
)

log = logging.getLogger("order_commands")

ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
FINAL_TELEGRAM_URL = os.getenv("FINAL_TELEGRAM_URL", "http://localhost:3000")

# Command → (task_type, reply text)
TASK_DONE_COMMANDS: dict[str, tuple[str, str]] = {
    "ban":        ("ban_hd",     "✅ Đã đánh dấu Bán HĐ"),
    "soan":       ("soan_hang",  "✅ Đã đánh dấu Soạn hàng"),
    "giao":       ("giao_hang",  "✅ Đã đánh dấu Giao hàng"),
    "nop tien":   ("nop_tien",   "✅ Đã đánh dấu Nộp tiền"),
    "nop":        ("nop_tien",   "✅ Đã đánh dấu Nộp tiền"),
    "nhan tien":  ("nhan_tien",  "✅ Đã đánh dấu Nhận tiền"),
    "nhan":       ("nhan_tien",  "✅ Đã đánh dấu Nhận tiền"),
    "xuat hd roi":("xuat_hd",    "✅ Đã đánh dấu Xuất HĐ"),
    "xuat hd":    ("xuat_hd",    "✅ Đã đánh dấu Xuất HĐ"),
}

CLEAR_COMMANDS: dict[str, str] = {
    "clear soan":      "soan_hang",
    "clear soan hang": "soan_hang",
    "clear giao":      "giao_hang",
    "clear giao hang": "giao_hang",
    "clear nop":       "nop_tien",
    "clear nop tien":  "nop_tien",
    "clear nhan":      "nhan_tien",
    "clear nhan tien": "nhan_tien",
}

CLEAR_REPLIES: dict[str, str] = {
    "soan_hang":  "♻️ Đã đặt lại trạng thái Soạn hàng",
    "giao_hang":  "♻️ Đã đặt lại trạng thái Giao hàng",
    "nop_tien":   "♻️ Đã đặt lại trạng thái Nộp tiền",
    "nhan_tien":  "♻️ Đã đặt lại trạng thái Nhận tiền",
}

SKIP_COMMANDS: dict[str, str] = {
    "skip nop tien": "nop_tien",
}


def _extract_thread_id(msg) -> int | None:
    """Extract thread/topic ID from a forum message. Same as gtr_handler.py."""
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


def _notify_refresh(thread_id: int):
    """Fire-and-forget POST to final_telegram to trigger updateView."""
    body = json.dumps({"thread_id": thread_id})
    log.debug("notifying refresh for thread=%d", thread_id)
    try:
        host_port = FINAL_TELEGRAM_URL.replace("http://", "").replace("https://", "")
        host, _, port_str = host_port.partition(":")
        port = int(port_str) if port_str else 80
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("POST", "/api/order/refresh-view", body, {
            "Content-Type": "application/json",
        })
        conn.close()
    except Exception as e:
        log.warning("Failed to notify refresh: %s", e)


def register_order_commands(client):
    """Attach all task command handlers. Called from server.py."""
    db_conn = _get_connection()
    log.info("order_commands listening on chat %d", ORDER_GROUP_ID)

    # ── Build command regex ──────────────────────────────────────────
    done_patterns = "|".join(re.escape(c) for c in TASK_DONE_COMMANDS)
    done_re = re.compile(rf"^(?:{done_patterns})$", re.IGNORECASE)

    clear_patterns = "|".join(re.escape(c) for c in CLEAR_COMMANDS)
    clear_re = re.compile(rf"^(?:{clear_patterns})$", re.IGNORECASE)

    skip_patterns = "|".join(re.escape(c) for c in SKIP_COMMANDS)
    skip_re = re.compile(rf"^(?:{skip_patterns})$", re.IGNORECASE)

    # ── Done commands ─────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_task_done(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return

        text = (msg.text or "").strip()
        m = done_re.match(text)
        if not m:
            return

        matched_text = m.group(0).lower()
        task_type, reply_text = TASK_DONE_COMMANDS[matched_text]

        thread_id = _extract_thread_id(msg)
        if not thread_id:
            log.warning("task_done: could not determine thread_id for msg %d", msg.id)
            await client.send_message(
                msg.chat_id,
                "❌ Không xác định được thread_id. Dùng lệnh này trong topic đơn hàng.",
                            )
            return

        sender_id = getattr(msg, "sender_id", None)
        log.debug("task_done: thread=%d task=%s user=%s", thread_id, task_type, sender_id)

        ok = set_task_status(db_conn, thread_id, task_type, sender_id)
        if ok:
            await client.send_message(msg.chat_id, reply_text)
            _notify_refresh(thread_id)
        else:
            await client.send_message(
                msg.chat_id,
                "❌ Không tìm thấy đơn hàng hoặc lỗi cập nhật.",
                            )

    # ── Clear commands ────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_task_clear(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return

        text = (msg.text or "").strip()
        m = clear_re.match(text)
        if not m:
            return

        matched_text = m.group(0).lower()
        task_type = CLEAR_COMMANDS[matched_text]
        reply_text = CLEAR_REPLIES.get(task_type, "♻️ Đã đặt lại trạng thái")

        thread_id = _extract_thread_id(msg)
        if not thread_id:
            await client.send_message(
                msg.chat_id,
                "❌ Không xác định được thread_id. Dùng lệnh này trong topic đơn hàng.",
                            )
            return

        sender_id = getattr(msg, "sender_id", None)
        log.debug("task_clear: thread=%d task=%s user=%s", thread_id, task_type, sender_id)

        ok = clear_task_status(db_conn, thread_id, task_type, sender_id)
        if ok:
            await client.send_message(msg.chat_id, reply_text)
            _notify_refresh(thread_id)
        else:
            await client.send_message(
                msg.chat_id,
                "❌ Không thể đặt lại trạng thái (lỗi không xác định).",
                            )

    # ── Skip commands ─────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_task_skip(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return

        text = (msg.text or "").strip()
        m = skip_re.match(text)
        if not m:
            return

        matched_text = m.group(0).lower()
        task_type = SKIP_COMMANDS[matched_text]

        thread_id = _extract_thread_id(msg)
        if not thread_id:
            await client.send_message(
                msg.chat_id,
                "❌ Không xác định được thread_id.",
                            )
            return

        sender_id = getattr(msg, "sender_id", None)
        log.debug("task_skip: thread=%d task=%s user=%s", thread_id, task_type, sender_id)

        ok = set_task_status(db_conn, thread_id, task_type, sender_id, skip=True)
        if ok:
            await client.send_message(msg.chat.id, "🔘 Đã bỏ qua Nộp tiền")
            _notify_refresh(thread_id)
        else:
            await client.send_message(
                msg.chat_id,
                "❌ Không thể bỏ qua (lỗi không xác định).",
                            )
