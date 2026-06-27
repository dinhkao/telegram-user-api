from __future__ import annotations

import logging
import time

from aiohttp import web
from vn import vn_normalize

from server_app.config import RESULT_CACHE_TTL_SEC, SEARCH_BATCH, SEARCH_MAX_DEEP
from server_app.formatters import sender_info
from server_app import state
from server_app.telegram_helpers import tg_get_messages

log = logging.getLogger("server")


def _msg_dict(msg, sender):
    return {"type": "new", "id": msg.id, "date": msg.date.isoformat(), "sender": sender_info(sender), "text": msg.text[:1000] if msg.text else None, "media": type(msg.media).__name__.replace("MessageMedia", "") if msg.media else None, "reply_to": msg.reply_to_msg_id}


async def _server_search(query: str, offset_id: int = 0):
    try:
        msgs = await tg_get_messages("me", search=query, limit=SEARCH_BATCH, offset_id=offset_id)
    except Exception as e:
        if "FLOOD_WAIT" in str(e).upper():
            raise
        log.error("Server search error: %s", e)
        return [], False, 0
    msgs = msgs if isinstance(msgs, list) else ([msgs] if msgs else [])
    nq = vn_normalize(query)
    results = [_msg_dict(m, {"name": "Saved Messages", "id": 0}) for m in msgs if (m.text or "") and nq in vn_normalize(m.text or "")]
    return results, len(msgs) >= SEARCH_BATCH, (msgs[-1].id if msgs else 0)


async def _deep_search(query: str, offset_id: int = 0):
    nq = vn_normalize(query)
    results = [m for m in state.recent_messages if nq in vn_normalize(m.get("text") or "")]
    if results:
        return results, False, 0, len(state.recent_messages)
    scanned, fetch_offset, has_more = 0, offset_id or (state.recent_messages[0]["id"] if state.recent_messages else 0), False
    while scanned < SEARCH_MAX_DEEP:
        try:
            batch = await tg_get_messages("me", limit=100, offset_id=fetch_offset)
        except Exception as e:
            if "FLOOD_WAIT" in str(e).upper():
                raise
            log.error("Deep scan fetch error: %s", e)
            break
        if not batch:
            break
        scanned += len(batch)
        batch = batch if isinstance(batch, list) else [batch]
        results = [_msg_dict(m, {"name": "Saved Messages", "id": 0}) for m in batch if nq in vn_normalize(m.message or "")]
        if results or scanned >= SEARCH_MAX_DEEP:
            has_more = scanned < SEARCH_MAX_DEEP and not results
            return results, has_more, (batch[-1].id if batch else 0), scanned
        fetch_offset = batch[-1].id
    return results, has_more, 0, scanned


async def search_handler(request: web.Request):
    q = request.query.get("q", "").strip()
    if not q:
        return web.json_response({"results": [], "searched": 0, "has_more": False, "next_offset": 0, "mode": None})
    if state._client is None:
        return web.json_response({"error": "Telegram client not connected yet"}, status=503)
    offset_id = int(request.query.get("offset", "0"))
    mode = request.query.get("mode", "auto")
    cache_key = f"{q}:{offset_id}:{mode}"
    now = time.monotonic()
    cached = state.RESULT_CACHE.get(cache_key)
    if cached and now - cached["ts"] < RESULT_CACHE_TTL_SEC:
        return web.json_response(cached["data"])
    results, has_more, next_offset, searched, used_mode = [], False, 0, 0, None
    if mode in ("auto", "server"):
        try:
            results, has_more, next_offset = await _server_search(q, offset_id)
            used_mode, searched = "server", len(results)
        except Exception as e:
            if "FLOOD_WAIT" in str(e).upper():
                return web.json_response({"error": "Telegram rate limit — wait a moment and try again"}, status=429)
    if not results and mode in ("auto", "deep"):
        try:
            results, has_more, next_offset, searched = await _deep_search(q, offset_id)
            used_mode = "deep"
        except Exception as e:
            if "FLOOD_WAIT" in str(e).upper():
                return web.json_response({"error": "Telegram rate limit — deep scan paused. Try again in a moment."}, status=429)
            log.error("Deep search error: %s", e)
    data = {"results": results, "searched": searched, "has_more": has_more, "next_offset": next_offset, "mode": used_mode}
    state.RESULT_CACHE[cache_key] = {"data": data, "ts": now}
    for k, v in [*state.RESULT_CACHE.items()]:
        if now - v["ts"] > RESULT_CACHE_TTL_SEC:
            del state.RESULT_CACHE[k]
    return web.json_response(data)
