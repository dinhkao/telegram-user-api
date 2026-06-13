"""order_chat_logger.py — Store all chat messages in order threads to SQLite.

Attaches a lightweight Telethon handler that listens on ORDER_GROUP_ID.
Every message sent as a reply in any thread is logged to order_chat_messages.
"""
from __future__ import annotations
import logging
import os
import sqlite3
from telethon import events
from telethon.tl.types import MessageService

log = logging.getLogger("chat_logger")

SHARED_DB_PATH = os.path.expanduser(
    os.getenv("SHARED_DB_PATH", "~/Documents/final_telegram/data/app.db")
)
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS order_chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id   INTEGER NOT NULL,
    message_id  INTEGER NOT NULL UNIQUE,
    sender_id   INTEGER,
    sender_name TEXT,
    text        TEXT,
    media_type  TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chat_thread ON order_chat_messages(thread_id);
"""


def init_table():
    """Create table and index if not exists. Call once at startup."""
    conn = sqlite3.connect(SHARED_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    conn.close()
    log.info("order_chat_messages table ready")


def _insert_msg(thread_id: int, msg_id: int, sender_id: int | None,
                sender_name: str | None, text: str | None, media_type: str | None) -> None:
    """Insert a single message row. Best-effort, never throws."""
    try:
        conn = sqlite3.connect(SHARED_DB_PATH)
        conn.execute("PRAGMA busy_timeout=2000")
        conn.execute(
            """INSERT OR IGNORE INTO order_chat_messages
               (thread_id, message_id, sender_id, sender_name, text, media_type)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (thread_id, msg_id, sender_id, sender_name, text, media_type),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def register_chat_logger(client):
    """Attach the chat logger handler. Called from server.py."""
    init_table()

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def _on_thread_message(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return

        # Only log messages that are replies in a thread
        thread_id = None
        if msg.reply_to:
            thread_id = (
                getattr(msg.reply_to, "reply_to_top_id", None)
                or getattr(msg.reply_to, "reply_to_msg_id", None)
            )
        if not thread_id:
            return

        # Extract data before offloading (Telethon objects not thread-safe)
        msg_id = msg.id
        sender_id = msg.sender_id if hasattr(msg, "sender_id") else None
        sender_name = None
        if sender_id and hasattr(msg, "sender") and msg.sender:
            sender_name = getattr(msg.sender, "first_name", None) or getattr(msg.sender, "title", None)

        media_type = None
        if msg.media:
            from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
            if isinstance(msg.media, MessageMediaPhoto):
                media_type = "photo"
            elif isinstance(msg.media, MessageMediaDocument):
                media_type = "document"
            else:
                media_type = "other"

        text = (msg.text or "").strip() or None
        if not text and not media_type:
            return

        # Offload to thread to avoid any blocking in event loop
        import asyncio
        await asyncio.to_thread(
            _insert_msg, thread_id, msg_id, sender_id, sender_name, text, media_type
        )

    log.info("chat_logger listening on chat %d", ORDER_GROUP_ID)
