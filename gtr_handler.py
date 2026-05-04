"""gtr_handler.py — Ultra-fast "gtr" reply via Telethon.

Listens for "gtr" in the order group chat. Extracts thread ID, validates the
order exists in SQLite, replies instantly via Telethon (direct MTProto, no
HTTP bridge), then fire-and-forgets the heavy DB write to final_telegram's
existing /api/order/nhan-tien endpoint.

Works exactly like what_data.py — same listener, same reply speed.
"""
from __future__ import annotations
import http.client
import json
import os
import sqlite3
import time
from datetime import datetime
from telethon import events
from telethon.tl.types import MessageService


ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
SHARED_DB_PATH = os.path.expanduser(
    os.getenv("SHARED_DB_PATH", "~/Documents/final_telegram/data/app.db")
)
TRIGGER_TEXT = "gtr"

# API endpoint on final_telegram for the actual DB work
FINAL_TELEGRAM_URL = os.getenv("FINAL_TELEGRAM_URL", "http://localhost:3000")


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


def _notify_final_telegram(thread_id: int, user_id: int | None):
    """Fire-and-forget: POST /api/order/nhan-tien to do the DB work."""
    body = json.dumps({
        "thread_id": thread_id,
        "user_id": user_id,
        "note": "gtr",
    })
    try:
        conn = http.client.HTTPConnection(
            FINAL_TELEGRAM_URL.replace("http://", "").replace("https://", "").split(":")[0],
            int(FINAL_TELEGRAM_URL.split(":")[-1]) if ":" in FINAL_TELEGRAM_URL else 80,
            timeout=5,
        )
        conn.request("POST", "/api/order/nhan-tien", body, {
            "Content-Type": "application/json",
        })
        # Don't wait for response — fire and forget
        conn.close()
    except Exception as e:
        print(f"[gtr] Failed to notify final_telegram: {e}")


def _get_connection():
    """Open a new read-only WAL connection."""
    conn = sqlite3.connect(
        f"file:{SHARED_DB_PATH}?mode=ro",
        uri=True,
        check_same_thread=False,
        isolation_level=None,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=2000;")
    return conn


def register_gtr_handler(client):
    """Attach the 'gtr' command handler. Called from server.py."""

    db_conn = _get_connection()
    print(
        f"[gtr] listening on chat {ORDER_GROUP_ID} "
        f"for '{TRIGGER_TEXT}'. DB: {SHARED_DB_PATH}"
    )

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_group_message(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return

        text = (msg.text or "").strip()
        if text.lower() != TRIGGER_TEXT:
            return

        thread_id = _extract_thread_id(msg)
        if not thread_id:
            await client.send_message(
                msg.chat_id,
                "❌ gtr: Không xác định được thread_id. Dùng lệnh này trong topic đơn hàng.",
                reply_to=msg.id,
            )
            return

        t0 = time.monotonic()
        order_text = ""

        try:
            order_text = _get_order_text(db_conn, thread_id) or ""
        except Exception:
            pass

        elapsed = (time.monotonic() - t0) * 1000

        if not order_text:
            await client.send_message(
                msg.chat_id,
                "❌ Không tìm thấy đơn hàng trong SQLite.",
                reply_to=msg.id,
            )
            return

        # Reply instantly via Telethon — ultra-fast, same as what_data
        await client.send_message(
            msg.chat_id,
            "✅ Đã đánh dấu Nhận tiền (gtr)",
            parse_mode="html",
            reply_to=msg.id,
        )

        # Fire-and-forget: call final_telegram to do the actual DB work
        sender_id = getattr(msg, "sender_id", None)
        _notify_final_telegram(thread_id, sender_id)

        who = getattr(msg, "sender_id", "?")
        print(
            f"[gtr] [{datetime.now():%H:%M:%S}] "
            f"thread={thread_id} text={order_text[:40]!r} "
            f"{elapsed:.1f}ms asked by {who} — reply sent, API notified"
        )
