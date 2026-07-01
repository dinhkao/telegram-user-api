from __future__ import annotations

import logging
import os
import sqlite3
import time

from telethon import events
from telethon.tl.types import MessageService

from order_db import get_order_by_thread_id, set_task_status

from .thread_utils import extract_thread_id

log = logging.getLogger("gtr")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
from utils.paths import SHARED_DB_PATH
from utils.db import get_connection
TRIGGER_TEXT = "gtr"


def _conn():
    return get_connection()


def _text(conn, thread_id: int):
    row = conn.execute("SELECT json_extract(json, '$.text') FROM orders WHERE thread_id = ? AND deleted_at IS NULL", (thread_id,)).fetchone()
    return None if row is None or row[0] is None else str(row[0])


def register_gtr_handler(client):
    db_conn = _conn()
    log.info("listening on chat %d for '%s'. DB: %s", ORDER_GROUP_ID, TRIGGER_TEXT, SHARED_DB_PATH)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_msg(event):
        msg = event.message
        if isinstance(msg, MessageService) or (msg.text or "").strip().lower() != TRIGGER_TEXT:
            return
        thread_id = extract_thread_id(msg)
        if not thread_id:
            await client.send_message(msg.chat_id, "❌ gtr: Không xác định được thread_id. Dùng lệnh này trong topic đơn hàng.", reply_to=msg.id)
            return
        t0 = time.monotonic()
        order_text = _text(db_conn, thread_id) or ""
        elapsed = (time.monotonic() - t0) * 1000
        if not order_text:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng trong SQLite.", reply_to=msg.id)
            return
        sender_id = getattr(msg, "sender_id", None)
        ok = set_task_status(db_conn, thread_id, "nhan_tien", sender_id, note="gtr")
        await client.send_message(msg.chat_id, "✅ Đã đánh dấu Nhận tiền (gtr)", parse_mode="html", reply_to=msg.id)
        if ok:
            try:
                order = get_order_by_thread_id(db_conn, thread_id)
                if order:
                    from firebase_sync import set_order as fb_set_order

                    try:
                        fb_set_order(thread_id, order)
                    except Exception:
                        pass
                    row = db_conn.execute("SELECT channel_id, message_id FROM orders WHERE thread_id = ? AND deleted_at IS NULL", (thread_id,)).fetchone()
                    if row and row["channel_id"] and row["message_id"]:
                        from order_commands_v3 import _refresh_order_message

                        client.loop.create_task(_refresh_order_message(client, db_conn, thread_id, row["channel_id"], row["message_id"]))
            except Exception as e:
                log.warning("gtr: refresh failed for thread=%d: %s", thread_id, e)
        log.info("thread=%d text=%r %.1fms asked by %s — reply sent, DB updated", thread_id, order_text[:40], elapsed, getattr(msg, "sender_id", "?"))
