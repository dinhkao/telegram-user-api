from __future__ import annotations

import asyncio
import logging
import os

from .core import _html_to_png
from .rendering import _send_photo

log = logging.getLogger("html_to_png")


def _normalize(data: dict):
    discussion_group_id = data.get("discussion_group_id")
    discussion_thread_id = data.get("discussion_group_thread_id")
    discussion_message_id = data.get("discussion_group_message_id")
    discussion_main_message_id = data.get("discussion_group_main_message_id")
    chat_id = discussion_group_id or data.get("chat_id")
    message_thread_id = discussion_thread_id or discussion_message_id or data.get("message_thread_id")
    reply_to_message_id = discussion_main_message_id or data.get("reply_to_message_id")
    return {
        "html": data.get("html"),
        "chat_id": chat_id,
        "message_thread_id": message_thread_id,
        "reply_to_message_id": reply_to_message_id,
        "is_discussion": any(x is not None for x in [discussion_group_id, discussion_thread_id, discussion_message_id, discussion_main_message_id]),
        "caption": data.get("caption"),
        "parse_mode": data.get("parse_mode"),
    }


def _process_job_sync(client, loop, ref, key, job):
    if not job["html"] or not job["chat_id"]:
        log.warning("Missing html or chat_id — skipping")
        return
    if job["is_discussion"] and not job["message_thread_id"]:
        log.warning("Discussion job missing message_thread_id — skipping")
        return
    photo_path = None
    try:
        photo_path = _html_to_png(job["html"], log)
        future = asyncio.run_coroutine_threadsafe(_send_photo(
            client, job["chat_id"], photo_path, job["reply_to_message_id"],
            job["message_thread_id"], job["caption"], job["parse_mode"], log,
        ), loop)
        future.result(timeout=60)
    except Exception as e:
        log.error("Job %s failed: %s", key or "single", e)
        return
    finally:
        if photo_path and os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except Exception:
                pass
    try:
        if key:
            ref.child(key).delete()
        else:
            ref.update({
                "html": None, "chat_id": None, "message_thread_id": None, "reply_to_message_id": None,
                "discussion_group_id": None, "discussion_group_thread_id": None,
                "discussion_group_message_id": None, "discussion_group_main_message_id": None,
            })
    except Exception as e:
        log.warning("Firebase cleanup failed: %s", e)
