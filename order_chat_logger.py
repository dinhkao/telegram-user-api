"""order_chat_logger.py — Store order-group chat activity to SQLite.

Attaches lightweight Telethon handlers that listen on ORDER_GROUP_ID.
Logs new/edited/deleted messages for forum threads into order_chat_messages.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import sqlite3
from telethon import events
from telethon.tl.types import MessageService

log = logging.getLogger("chat_logger")

SHARED_DB_PATH = os.path.expanduser(
    os.getenv("SHARED_DB_PATH", "~/letrang-db/app.db")
)
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS order_chat_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id    INTEGER NOT NULL,
    message_id   INTEGER NOT NULL UNIQUE,
    sender_id    INTEGER,
    sender_name  TEXT,
    text         TEXT,
    media_type   TEXT,
    event_type   TEXT DEFAULT 'new',
    raw_json     TEXT,
    created_at   TEXT DEFAULT (datetime('now')),
    edited_at    TEXT,
    deleted_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_chat_thread ON order_chat_messages(thread_id);
"""


def _connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(SHARED_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    return conn


def _table_columns(conn: sqlite3.Connection) -> set[str]:
    cur = conn.execute("PRAGMA table_info(order_chat_messages)")
    return {row[1] for row in cur.fetchall()}


def _migrate_table(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn)
    added_columns: list[str] = []

    if "event_type" not in columns:
        conn.execute("ALTER TABLE order_chat_messages ADD COLUMN event_type TEXT DEFAULT 'new'")
        added_columns.append("event_type")
    if "raw_json" not in columns:
        conn.execute("ALTER TABLE order_chat_messages ADD COLUMN raw_json TEXT")
        added_columns.append("raw_json")
    if "edited_at" not in columns:
        conn.execute("ALTER TABLE order_chat_messages ADD COLUMN edited_at TEXT")
        added_columns.append("edited_at")
    if "deleted_at" not in columns:
        conn.execute("ALTER TABLE order_chat_messages ADD COLUMN deleted_at TEXT")
        added_columns.append("deleted_at")

    # Old rows from the legacy logger are still "new" messages.
    conn.execute(
        "UPDATE order_chat_messages SET event_type = 'new' "
        "WHERE event_type IS NULL AND deleted_at IS NULL"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_thread ON order_chat_messages(thread_id)")
    conn.commit()

    if added_columns:
        log.info("order_chat_messages migrated: added columns %s", ", ".join(added_columns))


def init_table():
    """Create table and index if not exists. Call once at startup."""
    conn = _connect_db()
    try:
        conn.executescript(_SCHEMA_SQL)
        _migrate_table(conn)
    finally:
        conn.close()
    log.info("order_chat_messages table ready")


def _safe_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _sender_name(msg) -> str | None:
    sender = getattr(msg, "sender", None)
    if not sender:
        return None

    first = getattr(sender, "first_name", None)
    last = getattr(sender, "last_name", None)
    if first or last:
        return " ".join(part for part in (first, last) if part)

    return getattr(sender, "title", None) or getattr(sender, "username", None)


def _media_type(msg) -> str | None:
    if isinstance(msg, MessageService):
        return "service"

    media = getattr(msg, "media", None)
    if not media:
        return None

    media_name = type(media).__name__
    if media_name.startswith("MessageMedia"):
        return media_name.removeprefix("MessageMedia").lower()
    return media_name.lower()


def _message_text(msg) -> str | None:
    if isinstance(msg, MessageService):
        action = getattr(msg, "action", None)
        return type(action).__name__ if action else None

    text = (getattr(msg, "raw_text", None) or getattr(msg, "text", None) or "").strip()
    return text or None


def _extract_thread_id(msg) -> int | None:
    thread_id = None
    if msg.reply_to:
        thread_id = (
            getattr(msg.reply_to, "reply_to_top_id", None)
            or getattr(msg.reply_to, "reply_to_msg_id", None)
        )

    if not thread_id:
        thread_id = getattr(msg, "reply_to_top_id", None) or getattr(msg, "reply_to_msg_id", None)

    if not thread_id:
        raw = getattr(msg, "_raw", None) or getattr(msg, "original_update", None)
        if raw:
            reply_to = getattr(raw, "reply_to", None)
            if reply_to:
                thread_id = (
                    getattr(reply_to, "reply_to_top_id", None)
                    or getattr(reply_to, "reply_to_msg_id", None)
                )

    if not thread_id and isinstance(msg, MessageService):
        action_name = type(getattr(msg, "action", None)).__name__
        if "TopicCreate" in action_name:
            thread_id = getattr(msg, "id", None)

    return thread_id


def _build_raw_json(msg, *, event_type: str, thread_id: int | None, extra: dict | None = None) -> str:
    payload = msg.to_dict() if hasattr(msg, "to_dict") else {"message_id": getattr(msg, "id", None)}
    if not isinstance(payload, dict):
        payload = {"payload": payload}
    payload.update(
        {
            "logger_event_type": event_type,
            "logger_thread_id": thread_id,
        }
    )
    if extra:
        payload.update(extra)
    return _safe_json(payload)


def _build_delete_raw_json(*, message_id: int, deleted_ids: list[int], chat_id: int | None) -> str:
    return _safe_json(
        {
            "logger_event_type": "delete",
            "message_id": message_id,
            "deleted_ids": deleted_ids,
            "chat_id": chat_id,
        }
    )


def _lookup_thread_id(message_id: int) -> int | None:
    conn = _connect_db()
    try:
        row = conn.execute(
            "SELECT thread_id FROM order_chat_messages WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        return row["thread_id"] if row else None
    finally:
        conn.close()


def _upsert_msg(
    *,
    thread_id: int,
    msg_id: int,
    sender_id: int | None,
    sender_name: str | None,
    text: str | None,
    media_type: str | None,
    event_type: str,
    raw_json: str,
) -> None:
    conn = _connect_db()
    try:
        conn.execute(
            """
            INSERT INTO order_chat_messages
                (thread_id, message_id, sender_id, sender_name, text,
                 media_type, event_type, raw_json, edited_at, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CASE WHEN ? = 'edit' THEN datetime('now') ELSE NULL END, NULL)
            ON CONFLICT(message_id) DO UPDATE SET
                thread_id = excluded.thread_id,
                sender_id = excluded.sender_id,
                sender_name = excluded.sender_name,
                text = excluded.text,
                media_type = excluded.media_type,
                event_type = excluded.event_type,
                raw_json = excluded.raw_json,
                edited_at = CASE
                    WHEN excluded.event_type = 'edit' THEN COALESCE(order_chat_messages.edited_at, datetime('now'))
                    ELSE order_chat_messages.edited_at
                END,
                deleted_at = NULL
            """,
            (thread_id, msg_id, sender_id, sender_name, text, media_type, event_type, raw_json, event_type),
        )
        conn.commit()
    finally:
        conn.close()


def _mark_deleted(msg_ids: list[int], raw_json_by_id: dict[int, str]) -> list[int]:
    conn = _connect_db()
    missing: list[int] = []
    try:
        for msg_id in msg_ids:
            cur = conn.execute(
                """
                UPDATE order_chat_messages
                SET deleted_at = datetime('now'),
                    event_type = 'delete',
                    raw_json = ?
                WHERE message_id = ?
                """,
                (raw_json_by_id[msg_id], msg_id),
            )
            if cur.rowcount == 0:
                missing.append(msg_id)
        conn.commit()
        return missing
    finally:
        conn.close()


def register_chat_logger(client):
    """Attach the chat logger handler. Called from server.py."""
    init_table()

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def _on_new_message(event):
        msg = event.message
        thread_id = _extract_thread_id(msg)
        if not thread_id:
            log.warning(
                "chat_logger: skip new message because thread_id is unknown "
                "msg_id=%s chat_id=%s sender_id=%s service=%s",
                getattr(msg, "id", None),
                getattr(msg, "chat_id", None),
                getattr(msg, "sender_id", None),
                isinstance(msg, MessageService),
            )
            return

        event_type = "service" if isinstance(msg, MessageService) else "new"
        sender_id = getattr(msg, "sender_id", None)
        sender_name = _sender_name(msg)
        media_type = _media_type(msg)
        text = _message_text(msg)
        raw_json = _build_raw_json(msg, event_type=event_type, thread_id=thread_id)

        try:
            await asyncio.to_thread(
                _upsert_msg,
                thread_id=thread_id,
                msg_id=msg.id,
                sender_id=sender_id,
                sender_name=sender_name,
                text=text,
                media_type=media_type,
                event_type=event_type,
                raw_json=raw_json,
            )
        except Exception:
            log.exception(
                "chat_logger: failed to persist new message msg_id=%s thread_id=%s chat_id=%s",
                msg.id,
                thread_id,
                getattr(msg, "chat_id", None),
            )
            return

        log.debug(
            "chat_logger: stored %s message msg_id=%s thread_id=%s",
            event_type,
            msg.id,
            thread_id,
        )

    @client.on(events.MessageEdited(chats=ORDER_GROUP_ID))
    async def _on_edited_message(event):
        msg = event.message
        thread_id = _extract_thread_id(msg)
        if not thread_id:
            try:
                thread_id = await asyncio.to_thread(_lookup_thread_id, msg.id)
            except Exception:
                log.exception(
                    "chat_logger: thread lookup failed for edited message msg_id=%s chat_id=%s",
                    msg.id,
                    getattr(msg, "chat_id", None),
                )
                return

        if not thread_id:
            log.warning(
                "chat_logger: skip edited message because thread_id is unknown "
                "msg_id=%s chat_id=%s sender_id=%s",
                msg.id,
                getattr(msg, "chat_id", None),
                getattr(msg, "sender_id", None),
            )
            return

        sender_id = getattr(msg, "sender_id", None)
        sender_name = _sender_name(msg)
        media_type = _media_type(msg)
        text = _message_text(msg)
        raw_json = _build_raw_json(msg, event_type="edit", thread_id=thread_id)

        try:
            await asyncio.to_thread(
                _upsert_msg,
                thread_id=thread_id,
                msg_id=msg.id,
                sender_id=sender_id,
                sender_name=sender_name,
                text=text,
                media_type=media_type,
                event_type="edit",
                raw_json=raw_json,
            )
        except Exception:
            log.exception(
                "chat_logger: failed to persist edited message msg_id=%s thread_id=%s chat_id=%s",
                msg.id,
                thread_id,
                getattr(msg, "chat_id", None),
            )
            return

        log.debug("chat_logger: stored edited message msg_id=%s thread_id=%s", msg.id, thread_id)

    @client.on(events.MessageDeleted(chats=ORDER_GROUP_ID))
    async def _on_deleted_message(event):
        deleted_ids = list(event.deleted_ids or [])
        if not deleted_ids:
            log.warning(
                "chat_logger: received delete event without deleted_ids chat_id=%s",
                getattr(event, "chat_id", None),
            )
            return

        raw_json_by_id = {
            msg_id: _build_delete_raw_json(
                message_id=msg_id,
                deleted_ids=deleted_ids,
                chat_id=getattr(event, "chat_id", None),
            )
            for msg_id in deleted_ids
        }

        try:
            missing_ids = await asyncio.to_thread(_mark_deleted, deleted_ids, raw_json_by_id)
        except Exception:
            log.exception(
                "chat_logger: failed to persist deleted messages deleted_ids=%s chat_id=%s",
                deleted_ids,
                getattr(event, "chat_id", None),
            )
            return

        if missing_ids:
            log.warning(
                "chat_logger: delete event had no matching rows deleted_ids=%s chat_id=%s",
                missing_ids,
                getattr(event, "chat_id", None),
            )
        else:
            log.debug(
                "chat_logger: marked deleted message ids=%s chat_id=%s",
                deleted_ids,
                getattr(event, "chat_id", None),
            )

    log.info("chat_logger listening on chat %d", ORDER_GROUP_ID)
