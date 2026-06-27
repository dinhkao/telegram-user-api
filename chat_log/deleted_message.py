from __future__ import annotations

import asyncio
import logging

from telethon import events

from .db import ORDER_GROUP_ID
from .persistence import mark_deleted
from .raw_json import build_delete_raw_json

log = logging.getLogger("chat_logger")


def attach_deleted_message_handler(client) -> None:
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
            msg_id: build_delete_raw_json(
                message_id=msg_id,
                deleted_ids=deleted_ids,
                chat_id=getattr(event, "chat_id", None),
            )
            for msg_id in deleted_ids
        }
        try:
            missing_ids = await asyncio.to_thread(mark_deleted, deleted_ids, raw_json_by_id)
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
            log.debug("chat_logger: marked deleted message ids=%s chat_id=%s", deleted_ids, getattr(event, "chat_id", None))
