from __future__ import annotations

from .db import connect_db


def lookup_thread_id(message_id: int) -> int | None:
    conn = connect_db()
    try:
        row = conn.execute(
            "SELECT thread_id FROM order_chat_messages WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        return row["thread_id"] if row else None
    finally:
        conn.close()


def upsert_msg(
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
    conn = connect_db()
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


def mark_deleted(msg_ids: list[int], raw_json_by_id: dict[int, str]) -> list[int]:
    conn = connect_db()
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
