from __future__ import annotations

import asyncio
import logging

from donhang_db import DonHangDB

from .shared import BACKFILL_CHUNK, BACKFILL_SLEEP, matches, serialize

log = logging.getLogger("donhang_indexer")


async def backfill(client, db: DonHangDB, chat_id: int, query: str, on_progress=None):
    if db.get_meta("backfill_done") == "1":
        log.info("backfill: already done")
        return {"status": "already_done", **db.stats()}
    offset_id = int(db.get_meta("backfill_oldest_seen") or 0)
    total_scanned = total_matched = 0
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
        matched = [serialize(m) for m in batch if matches(m, query)]
        if matched:
            db.upsert_many(matched)
            total_matched += len(matched)
        total_scanned += len(batch)
        offset_id = batch[-1].id
        db.set_meta("backfill_oldest_seen", str(offset_id))
        log.debug("backfill chunk: scanned=%d matched=%d oldest=%d", total_scanned, total_matched, offset_id)
        if on_progress:
            on_progress(scanned=total_scanned, matched=total_matched, oldest_id=offset_id)
        if offset_id <= 1 or len(batch) < BACKFILL_CHUNK:
            log.info("backfill: reached channel start, done.")
            db.set_meta("backfill_done", "1")
            break
        await asyncio.sleep(BACKFILL_SLEEP)
    return {"status": "done", "scanned": total_scanned, "matched": total_matched, **db.stats()}
