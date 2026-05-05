"""what_data.py — Fast raw-data lookup for orders from group topic messages.

Listens for "what data" in the order group chat. Extracts the topic/thread ID,
queries the shared final_telegram SQLite database directly, and replies with
the raw order JSON.

Fits into server.py's register_handlers(client) call.
"""
from __future__ import annotations
import json
import logging
import sqlite3
import time
import os
from telethon import events
from telethon.tl.types import MessageService

log = logging.getLogger("what_data")

# The main order group where each order is a forum topic
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))

# Path to the shared SQLite database owned by final_telegram
SHARED_DB_PATH = os.path.expanduser(
    os.getenv("SHARED_DB_PATH", "~/Documents/final_telegram/data/app.db")
)

# Trigger text (case-insensitive comparison)
TRIGGER_TEXT = "what data"


def _get_order_raw(conn, thread_id: int) -> dict | None:
    """Query the orders table by thread_id. Returns the full JSON or None."""
    row = conn.execute(
        "SELECT json FROM orders WHERE thread_id = ? AND deleted_at IS NULL",
        (thread_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return {"_raw": str(row[0])}


def _format_reply(data: dict | None, thread_id: int, elapsed_ms: float) -> str:
    """Build a compact reply message for the raw data."""
    header = f"<b>Order data</b> (thread {thread_id}, {elapsed_ms:.1f}ms)\n\n"
    if data is None:
        return header + "❌ <i>Order not found in SQLite</i>"
    try:
        pretty = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pretty = str(data)
    if len(pretty) > 3800:
        pretty = pretty[:3800] + "\n\n... [truncated]"
    return header + f"<pre>{_escape_html(pretty)}</pre>"


def _escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _get_connection():
    """Open a new read-only WAL connection (fast, no schema changes)."""
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


def register_what_data_handler(client):
    """Attach the 'what data' event handler. Called from server.py."""

    db_conn = _get_connection()
    log.info("listening on chat %d for '%s'. DB: %s", ORDER_GROUP_ID, TRIGGER_TEXT, SHARED_DB_PATH)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_order_group_message(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return

        text = (msg.text or "").strip()
        if text.lower() != TRIGGER_TEXT:
            return

        log.debug("what_data triggered by sender=%s", getattr(msg, "sender_id", "?"))

        # Extract topic/thread ID (forum topics use reply_to.reply_to_top_id)
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

        if not thread_id:
            log.warning("what_data: could not determine thread_id for msg %d", msg.id)
            await client.send_message(
                msg.chat_id,
                "❌ Could not determine thread_id from this message.",
                reply_to=msg.id,
            )
            return

        log.debug("what_data: extracted thread_id=%d for msg %d", thread_id, msg.id)

        t0 = time.monotonic()
        try:
            data = _get_order_raw(db_conn, thread_id)
        except Exception as e:
            log.error("what_data DB error: thread=%d error=%s", thread_id, e)
            await client.send_message(
                msg.chat_id,
                f"❌ DB error: {e}",
                reply_to=msg.id,
            )
            return

        elapsed = (time.monotonic() - t0) * 1000
        reply_text = _format_reply(data, thread_id, elapsed)

        await client.send_message(
            msg.chat_id,
            reply_text,
            parse_mode="html",
            reply_to=msg.id,
        )
        who = getattr(msg, "sender_id", "?")
        log.info("thread=%d found=%s %.1fms asked by %s", thread_id, data is not None, elapsed, who)
