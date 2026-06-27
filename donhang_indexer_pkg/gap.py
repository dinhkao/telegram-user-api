from __future__ import annotations

from donhang_db import DonHangDB

from .shared import matches, serialize


async def fill_gap_to_newest(client, db: DonHangDB, chat_id: int, query: str):
    last_id = db.stats()["max_id"] or 0
    if last_id == 0:
        return 0
    new_msgs = []
    async for msg in client.iter_messages(chat_id, min_id=last_id):
        if matches(msg, query):
            new_msgs.append(serialize(msg))
    if new_msgs:
        db.upsert_many(new_msgs)
    return len(new_msgs)
