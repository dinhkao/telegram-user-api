from __future__ import annotations

import logging

from telethon import events

from donhang_db import DonHangDB

from .shared import matches, serialize

log = logging.getLogger("donhang_indexer")


def register_live_handlers(client, db: DonHangDB, chat_id: int, query: str, on_new_donhang=None):
    @client.on(events.NewMessage(chats=chat_id))
    async def _on_new(event):
        msg = event.message
        if matches(msg, query):
            db.upsert(serialize(msg))
            log.debug("donhang live: new msg id=%d indexed", msg.id)
            if on_new_donhang:
                try:
                    await on_new_donhang(msg.text or "", msg.id)
                except Exception:
                    log.warning("donhang auto-parse callback failed", exc_info=True)
    @client.on(events.MessageEdited(chats=chat_id))
    async def _on_edit(event):
        msg = event.message
        if matches(msg, query):
            db.upsert(serialize(msg))
            log.debug("donhang live: edited msg id=%d indexed", msg.id)
        elif db.has_id(msg.id):
            db.mark_deleted([msg.id])
            log.debug("donhang live: msg id=%d un-indexed (hashtag removed)", msg.id)
    @client.on(events.MessageDeleted(chats=chat_id))
    async def _on_delete(event):
        ids = event.deleted_ids or []
        if ids:
            n = db.mark_deleted(ids)
            log.debug("donhang live: deleted %d msgs %s", n, ids)
