"""gtr_handler.py — Ultra-fast "gtr" reply via Telethon.

Listens for "gtr" in the order group chat. Extracts thread ID, validates the
order exists in SQLite, replies instantly via Telethon (direct MTProto), then
updates nhan_tien task_status directly in SQLite and refreshes the main message.
"""
from __future__ import annotations
import logging
import os
import sqlite3
import time
from telethon import events
from telethon.tl.types import MessageService

log = logging.getLogger("gtr")

ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
SHARED_DB_PATH = os.path.expanduser(
    os.getenv("SHARED_DB_PATH", "~/Documents/final_telegram/data/app.db")
)
TRIGGER_TEXT = "gtr"


def _get_order_text(conn, thread_id: int) -> str | None:
    """Quick read: get order text from SQLite. Returns None if not found."""
    row = conn.execute(
        "SELECT json_extract(json, '$.text') FROM orders WHERE thread_id = ? AND deleted_at IS NULL",
        (thread_id,),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return str(row[0])


def _extract_thread_id(msg) -> int | None:
    """Extract thread/topic ID from a forum message. Same logic as what_data.py."""
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


def _get_connection():
    """Open a new read-write WAL connection."""
    conn = sqlite3.connect(
        SHARED_DB_PATH,
        check_same_thread=False,
        isolation_level=None,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def register_gtr_handler(client):
    """Attach the 'gtr' command handler. Called from server.py."""

    db_conn = _get_connection()
    log.info("listening on chat %d for '%s'. DB: %s", ORDER_GROUP_ID, TRIGGER_TEXT, SHARED_DB_PATH)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_group_message(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return

        text = (msg.text or "").strip()
        if text.lower() != TRIGGER_TEXT:
            return

        log.debug("gtr triggered by sender=%s", getattr(msg, "sender_id", "?"))

        thread_id = _extract_thread_id(msg)
        if not thread_id:
            log.warning("gtr: could not determine thread_id for msg %d", msg.id)
            await client.send_message(
                msg.chat_id,
                "❌ gtr: Không xác định được thread_id. Dùng lệnh này trong topic đơn hàng.",
                reply_to=msg.id,
            )
            return

        log.debug("gtr: extracted thread_id=%d for msg %d", thread_id, msg.id)

        t0 = time.monotonic()
        order_text = ""

        try:
            order_text = _get_order_text(db_conn, thread_id) or ""
        except Exception:
            pass

        elapsed = (time.monotonic() - t0) * 1000

        if not order_text:
            log.info("gtr: thread=%d order not found in SQLite", thread_id)
            await client.send_message(
                msg.chat_id,
                "❌ Không tìm thấy đơn hàng trong SQLite.",
                reply_to=msg.id,
            )
            return

        sender_id = getattr(msg, "sender_id", None)

        # ── 1. Update nhan_tien directly in SQLite ─────────────────
        from order_db import set_task_status, get_order_by_thread_id
        ok = set_task_status(db_conn, thread_id, "nhan_tien", sender_id, note="gtr")
        if not ok:
            log.warning("gtr: set_task_status failed for thread=%d", thread_id)

        # ── 2. Reply instantly ─────────────────────────────────────
        await client.send_message(
            msg.chat_id,
            "✅ Đã đánh dấu Nhận tiền (gtr)",
            parse_mode="html",
            reply_to=msg.id,
        )

        # ── 3. Refresh main order message + Firebase sync ───────────
        if ok:
            try:
                order = get_order_by_thread_id(db_conn, thread_id)
                if order:
                    # Firebase sync
                    from firebase_sync import set_order as fb_set_order
                    try:
                        fb_set_order(thread_id, order)
                    except Exception:
                        pass
                    # Refresh channel post
                    row = db_conn.execute(
                        "SELECT channel_id, message_id FROM orders WHERE thread_id = ? AND deleted_at IS NULL",
                        (thread_id,),
                    ).fetchone()
                    channel_id = row["channel_id"] if row else None
                    message_id = row["message_id"] if row else None
                    if channel_id and message_id:
                        from order_commands_v3 import _refresh_order_message
                        client.loop.create_task(
                            _refresh_order_message(client, db_conn, thread_id, channel_id, message_id)
                        )
            except Exception as e:
                log.warning("gtr: refresh failed for thread=%d: %s", thread_id, e)

        who = getattr(msg, "sender_id", "?")
        log.info("thread=%d text=%r %.1fms asked by %s — reply sent, DB updated",
                 thread_id, order_text[:40], elapsed, who)
