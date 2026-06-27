from __future__ import annotations

import asyncio
import logging

from telethon import events
from telethon.tl.types import MessageService

from .db import ORDER_GROUP_ID
from .message_extract import extract_thread_id, media_type, message_text, sender_name
from .raw_json import build_raw_json
from .persistence import upsert_msg

log = logging.getLogger("chat_logger")


def attach_new_message_handler(client) -> None:
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def _on_new_message(event):
        msg = event.message
        thread_id = extract_thread_id(msg)
        if not thread_id:
            log.warning(
                "chat_logger: skip new message because thread_id is unknown msg_id=%s chat_id=%s sender_id=%s service=%s",
                getattr(msg, "id", None),
                getattr(msg, "chat_id", None),
                getattr(msg, "sender_id", None),
                isinstance(msg, MessageService),
            )
            return
        event_type = "service" if isinstance(msg, MessageService) else "new"
        try:
            await asyncio.to_thread(
                upsert_msg,
                thread_id=thread_id,
                msg_id=msg.id,
                sender_id=getattr(msg, "sender_id", None),
                sender_name=sender_name(msg),
                text=message_text(msg),
                media_type=media_type(msg),
                event_type=event_type,
                raw_json=build_raw_json(msg, event_type=event_type, thread_id=thread_id),
            )
        except Exception:
            log.exception(
                "chat_logger: failed to persist new message msg_id=%s thread_id=%s chat_id=%s",
                msg.id,
                thread_id,
                getattr(msg, "chat_id", None),
            )
            return
        log.debug("chat_logger: stored %s message msg_id=%s thread_id=%s", event_type, msg.id, thread_id)
