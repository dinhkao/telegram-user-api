"""bot_core/utils.py — Shared helpers."""
import asyncio
import json
import logging
import unicodedata

import aiohttp

log = logging.getLogger("bot.utils")

_processed: set[str] = set()


def dedupe_key(event) -> str:
    return f"{event.chat_id}:{event.id}:{event.text or ''}"


def mark_once(event, ttl: int = 60) -> bool:
    key = dedupe_key(event)
    if key in _processed:
        return False
    if len(_processed) > 10000:
        _processed.clear()
    _processed.add(key)
    asyncio.get_running_loop().call_later(ttl, lambda: _processed.discard(key))
    return True


_NORM_TRANS = str.maketrans({
    'đ': 'd', 'Đ': 'D',
})


def _norm(text: str) -> str:
    """Normalize Vietnamese text for comparisons (NFD strip diacritics + lower + strip)."""
    text = str(text or "").translate(_NORM_TRANS)
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower().strip()


def is_cancel(text: str) -> bool:
    """Check if text means 'cancel' (handles Huỷ/hủy/HUY/huy)."""
    return _norm(text) == "huy"


def esc_html(s: str) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


_shared_session: aiohttp.ClientSession | None = None

async def _get_session() -> aiohttp.ClientSession:
    global _shared_session
    if _shared_session is None or _shared_session.closed:
        _shared_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    return _shared_session

async def post_json(url: str, data: dict) -> dict | None:
    try:
        sess = await _get_session()
        async with sess.post(url, json=data, headers={"Content-Type": "application/json"}) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"HTTP {resp.status}: {text}")
            return await resp.json()
    except Exception as e:
        log.error("POST %s failed: %s", url, e)
        raise


def name_of_user_id(uid) -> str | None:
    from bot_core.config import USER_NAMES
    return USER_NAMES.get(str(uid))

async def mark_task(s, task_type: str, user_id: int, **kwargs) -> bool:
    """Call task API + refresh session task_status. Returns True on success."""
    from bot_core import db
    from bot_flows._helpers import ORDER_API_BASE
    try:
        data = {"thread_id": s.thread_id, "user_id": user_id, **kwargs}
        await post_json(f"{ORDER_API_BASE}/api/order/{task_type}", data)
        fresh = db.get_order_by_thread(s.thread_id)
        if fresh:
            s.task_status = fresh.get("task_status")
        return True
    except Exception as e:
        log.error("mark_task %s error: %s", task_type, e)
        return False
