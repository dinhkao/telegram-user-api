from __future__ import annotations

from telethon.tl.types import MessageService

BACKFILL_CHUNK = 200
BACKFILL_SLEEP = 0.05


def serialize(msg) -> dict:
    return {"id": msg.id, "date": msg.date.isoformat() if msg.date else None, "text": msg.text or "", "raw_text": msg.raw_text or "", "media": type(msg.media).__name__.replace("MessageMedia", "") if msg.media else None, "reply_to": msg.reply_to_msg_id}


def matches(msg, query: str) -> bool:
    return not isinstance(msg, MessageService) and (query in (msg.text or "") or query in (msg.raw_text or ""))
