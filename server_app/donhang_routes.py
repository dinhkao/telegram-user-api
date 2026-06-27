from __future__ import annotations

import logging

from aiohttp import web

from donhang_db import DonHangDB

from server_app.config import DON_HANG_BATCH, DON_HANG_CHAT_ID, DON_HANG_DB_PATH, DON_HANG_QUERY
from server_app import state
from server_app.telegram_helpers import tg_get_messages

log = logging.getLogger("server")


async def donhang_handler(request: web.Request):
    if state._client is None:
        return web.json_response({"error": "Telegram client not connected yet"}, status=503)
    offset_id = int(request.query.get("offset", "0"))
    q = request.query.get("q", "").strip()
    mode = request.query.get("mode", "db")
    # if mode == "live":
    #     return await _donhang_live(offset_id)
    if mode == "server":
        return await _donhang_server(offset_id)
    if state._donhang_db is None:
        return web.json_response({"error": "DB not initialized"}, status=503)
    rows = state._donhang_db.search(q, offset_id=offset_id, limit=DON_HANG_BATCH) if q else state._donhang_db.page(offset_id=offset_id, limit=DON_HANG_BATCH)
    results = [{"id": r["id"], "date": r["date"], "text": (r["text"] or "")[:2000], "media": r["media"], "reply_to": r["reply_to"]} for r in rows]
    return web.json_response({"results": results, "has_more": len(rows) >= DON_HANG_BATCH, "next_offset": rows[-1]["id"] if rows else 0, "mode": "db", "query": q})


async def donhang_stats_handler(request: web.Request):
    return web.json_response(state._donhang_db.stats() if state._donhang_db else {"error": "DB not initialized"}, status=503 if state._donhang_db is None else 200)


async def _donhang_server(offset_id: int):
    try:
        msgs = await tg_get_messages(DON_HANG_CHAT_ID, search=DON_HANG_QUERY, limit=DON_HANG_BATCH, offset_id=offset_id)
    except Exception as e:
        return web.json_response({"error": "Telegram rate limit"}, status=429) if "FLOOD_WAIT" in str(e).upper() else web.json_response({"error": str(e)}, status=500)
    msgs = msgs if isinstance(msgs, list) else ([msgs] if msgs else [])
    return web.json_response({"results": [{"id": m.id, "date": m.date.isoformat() if m.date else None, "text": (m.text or "")[:2000]} for m in msgs if m.text], "has_more": len(msgs) >= DON_HANG_BATCH, "next_offset": msgs[-1].id if msgs else 0, "mode": "server"})


# async def _donhang_live(offset_id: int):
#     results, scanned, last_id = [], 0, offset_id
#     try:
#         kwargs = {"limit": 500, **({"offset_id": offset_id} if offset_id else {})}
#         async for msg in state._client.iter_messages(DON_HANG_CHAT_ID, **kwargs):
#             scanned += 1
#             last_id = msg.id
#             if DON_HANG_QUERY in (msg.text or ""):
#                 results.append({"id": msg.id, "date": msg.date.isoformat() if msg.date else None, "text": (msg.text or "")[:2000], "media": type(msg.media).__name__.replace("MessageMedia", "") if msg.media else None, "reply_to": msg.reply_to_msg_id})
#                 if len(results) >= DON_HANG_BATCH:
#                     break
#     except Exception as e:
#         return web.json_response({"error": "Telegram rate limit"}, status=429) if "FLOOD_WAIT" in str(e).upper() else web.json_response({"error": str(e)}, status=500)
#     return web.json_response({"results": results, "has_more": scanned >= 500 or len(results) >= DON_HANG_BATCH, "next_offset": last_id, "scanned": scanned, "mode": "live"})


async def donhang_page_handler(request: web.Request):
    return web.FileResponse("static/donhang.html")


async def donhang_msg_handler(request: web.Request):
    if state._client is None:
        return web.json_response({"error": "Telegram client not connected yet"}, status=503)
    try:
        mid = int(request.query.get("id", "0"))
    except ValueError:
        return web.json_response({"error": "bad id"}, status=400)
    msg = await tg_get_messages(DON_HANG_CHAT_ID, ids=mid)
    if msg is None:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response({"id": msg.id, "date": msg.date.isoformat() if msg.date else None, "text": msg.text or "", "raw_text": msg.raw_text or "", "message": msg.message or "", "has_hashtag_donhang_in_text": "#don_hang" in (msg.text or ""), "has_hashtag_donhang_in_raw": "#don_hang" in (msg.raw_text or ""), "media": type(msg.media).__name__ if msg.media else None})
