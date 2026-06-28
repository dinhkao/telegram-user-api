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


async def post_json(url: str, data: dict) -> dict | None:
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.post(
                url, json=data, headers={"Content-Type": "application/json"}
            ) as resp:
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
