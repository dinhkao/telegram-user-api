from __future__ import annotations

import logging

from donhang_db import DonHangDB
from donhang_indexer import backfill, fill_gap_to_newest, register_live_handlers

from server_app.config import DON_HANG_BATCH, DON_HANG_CHAT_ID, DON_HANG_DB_PATH, DON_HANG_QUERY
from server_app.state import set_donhang_db

log = logging.getLogger("server")


def init_donhang_db():
    db = DonHangDB(DON_HANG_DB_PATH)
    set_donhang_db(db)
    log.info("#don_hang DB: %s — %s", DON_HANG_DB_PATH, db.stats())
    return db


def register_donhang_live(client, db):
    register_live_handlers(client, db, DON_HANG_CHAT_ID, DON_HANG_QUERY)


async def bootstrap_donhang(client, db):
    try:
        gained = await fill_gap_to_newest(client, db, DON_HANG_CHAT_ID, DON_HANG_QUERY)
        if gained:
            log.info("#don_hang gap-fill: +%d new messages", gained)
        res = await backfill(client, db, DON_HANG_CHAT_ID, DON_HANG_QUERY, on_progress=lambda s, m, o: log.info("#don_hang backfill: scanned=%d matched=%d oldest=%d", s, m, o))
        log.info("#don_hang backfill: %s", res)
    except Exception as e:
        log.warning("#don_hang backfill error: %s", e)
