from __future__ import annotations

import asyncio
import logging

from telethon import events

from .db import ORDER_GROUP_ID
from .message_extract import extract_thread_id, media_type, message_text, sender_name
from .persistence import lookup_thread_id, upsert_msg
from .raw_json import build_raw_json

log = logging.getLogger("chat_logger")


def attach_edited_message_handler(client) -> None:
    @client.on(events.MessageEdited(chats=ORDER_GROUP_ID))
    async def _on_edited_message(event):
        msg = event.message
        thread_id = extract_thread_id(msg)
        if not thread_id:
            try:
                thread_id = await asyncio.to_thread(lookup_thread_id, msg.id)
            except Exception:
                log.exception(
                    "chat_logger: thread lookup failed for edited message msg_id=%s chat_id=%s",
                    msg.id,
                    getattr(msg, "chat_id", None),
                )
                return
        if not thread_id:
            log.warning(
                "chat_logger: skip edited message because thread_id is unknown msg_id=%s chat_id=%s sender_id=%s",
                msg.id,
                getattr(msg, "chat_id", None),
                getattr(msg, "sender_id", None),
            )
            return
        try:
            await asyncio.to_thread(
                upsert_msg,
                thread_id=thread_id,
                msg_id=msg.id,
                sender_id=getattr(msg, "sender_id", None),
                sender_name=sender_name(msg),
                text=message_text(msg),
                media_type=media_type(msg),
                event_type="edit",
                raw_json=build_raw_json(msg, event_type="edit", thread_id=thread_id),
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
