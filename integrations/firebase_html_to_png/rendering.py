from __future__ import annotations

import asyncio
import logging
import os

from .core import _executor, _html_to_png


async def _send_photo(client, chat_id, photo_path, reply_to, message_thread_id, caption, parse_mode, log):
    entity = await client.get_entity(chat_id)
    reply_to_id = reply_to or message_thread_id
    await client.send_file(entity, photo_path, reply_to=reply_to_id, caption=caption, parse_mode=parse_mode)
    log.info("Sent photo to %s (reply_to=%s thread=%s)", chat_id, reply_to, message_thread_id)


async def render_and_send_html(client, html: str, chat_id: int, thread_id: int,
                               reply_to: int | None = None, caption: str = "",
                               parse_mode: str = "html", log=None) -> str | None:
    log = log or logging.getLogger("html_to_png")
    loop = client.loop or asyncio.get_running_loop()
    photo_path = await loop.run_in_executor(_executor, _html_to_png, html, log)
    try:
        await _send_photo(client, chat_id, photo_path, reply_to, thread_id, caption, parse_mode, log)
        return photo_path
    except Exception:
        if photo_path and os.path.exists(photo_path):
            os.remove(photo_path)
        raise
