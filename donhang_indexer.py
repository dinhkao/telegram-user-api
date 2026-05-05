"""donhang_indexer.py — Backfill + live indexer for #don_hang messages.

Provides:
- backfill(client, db, chat_id, query, on_progress=None) — one-time full scan.
- register_live_handlers(client, db, chat_id, query) — keeps DB fresh via events.

Runs the backfill in chunks, persisting progress in meta('backfill_oldest_seen').
On restart, resumes from the last seen oldest id (continues older).
Once the channel start (id ≤ 1 or no more) is reached, sets meta('backfill_done')='1'.
"""
from __future__ import annotations
import asyncio
import logging
from telethon import events
from telethon.tl.types import MessageService

from donhang_db import DonHangDB

log = logging.getLogger("donhang_indexer")

BACKFILL_CHUNK = 200  # msgs fetched per iter_messages batch
BACKFILL_SLEEP = 0.05  # tiny delay between batches to avoid floodwait


def _serialize(msg) -> dict:
    return {
        "id": msg.id,
        "date": msg.date.isoformat() if msg.date else None,
        "text": msg.text or "",
        "raw_text": msg.raw_text or "",
        "media": type(msg.media).__name__.replace("MessageMedia", "") if msg.media else None,
        "reply_to": msg.reply_to_msg_id,
    }


def _matches(msg, query: str) -> bool:
    if isinstance(msg, MessageService):
        return False
    text = msg.text or ""
    raw = msg.raw_text or ""
    return query in text or query in raw


async def backfill(client, db: DonHangDB, chat_id: int, query: str, on_progress=None):
    """Scan from newest down to oldest, indexing every message that contains `query`.
    Resumable: stores the oldest id seen so far in meta.
    """
    if db.get_meta("backfill_done") == "1":
        log.info("backfill: already done")
        return {"status": "already_done", **db.stats()}

    # Resume from where we left off; offset_id=0 means start from newest.
    resume = db.get_meta("backfill_oldest_seen")
    offset_id = int(resume) if resume else 0

    total_scanned = 0
    total_matched = 0

    log.info("backfill: starting from offset_id=%d", offset_id)

    while True:
        kwargs = {"limit": BACKFILL_CHUNK}
        if offset_id:
            kwargs["offset_id"] = offset_id
        batch = []
        async for msg in client.iter_messages(chat_id, **kwargs):
            batch.append(msg)
        if not batch:
            log.info("backfill: no more messages, done.")
            db.set_meta("backfill_done", "1")
            break

        matches = [_serialize(m) for m in batch if _matches(m, query)]
        if matches:
            db.upsert_many(matches)
            total_matched += len(matches)
        total_scanned += len(batch)
        offset_id = batch[-1].id
        db.set_meta("backfill_oldest_seen", str(offset_id))

        log.debug("backfill chunk: scanned=%d matched=%d oldest=%d", total_scanned, total_matched, offset_id)

        if on_progress:
            on_progress(scanned=total_scanned, matched=total_matched, oldest_id=offset_id)

        # Reached start of channel
        if offset_id <= 1 or len(batch) < BACKFILL_CHUNK:
            log.info("backfill: reached channel start, done.")
            db.set_meta("backfill_done", "1")
            break

        await asyncio.sleep(BACKFILL_SLEEP)

    return {
        "status": "done",
        "scanned": total_scanned,
        "matched": total_matched,
        **db.stats(),
    }


def register_live_handlers(client, db: DonHangDB, chat_id: int, query: str):
    """Register Telethon handlers to keep the DB in sync with new/edited/deleted msgs."""

    @client.on(events.NewMessage(chats=chat_id))
    async def _on_new(event):
        msg = event.message
        if _matches(msg, query):
            db.upsert(_serialize(msg))
            log.debug("donhang live: new msg id=%d indexed", msg.id)

    @client.on(events.MessageEdited(chats=chat_id))
    async def _on_edit(event):
        msg = event.message
        if _matches(msg, query):
            db.upsert(_serialize(msg))
            log.debug("donhang live: edited msg id=%d indexed", msg.id)
        else:
            if db.has_id(msg.id):
                db.mark_deleted([msg.id])
                log.debug("donhang live: msg id=%d un-indexed (hashtag removed)", msg.id)

    @client.on(events.MessageDeleted(chats=chat_id))
    async def _on_delete(event):
        ids = event.deleted_ids or []
        if ids:
            n = db.mark_deleted(ids)
            log.debug("donhang live: deleted %d msgs %s", n, ids)


async def fill_gap_to_newest(client, db: DonHangDB, chat_id: int, query: str):
    """After a restart, fetch any messages newer than db.max_id that we missed.
    Keeps the DB current even if the server was offline for a while.
    Returns number of new messages added.
    Skips when DB is empty — backfill handles that case from newest down.
    """
    s = db.stats()
    last_id = s["max_id"] or 0
    if last_id == 0:
        return 0  # let backfill handle a fresh DB from newest down

    log.debug("donhang gap-fill: fetching msgs newer than %d", last_id)
    new_msgs = []
    async for msg in client.iter_messages(chat_id, min_id=last_id):
        if _matches(msg, query):
            new_msgs.append(_serialize(msg))

    if new_msgs:
        db.upsert_many(new_msgs)
    return len(new_msgs)
