"""tg_send_file.py — POST /api/tg/send-file.

Sends a Telegram file (photo, video, document) via the user account (Telethon).
Useful for forwarding media when bot accounts have stricter limits.

Multipart form-data:
    chat_id      int   (required, e.g. -1002124542200)
    file         file  (required, the file to send)
    caption      str   (optional)
    reply_to     int   (optional, message ID / thread ID to reply to)
    force_doc    bool  (optional, default True — send as document)

Auth: requires header `X-API-Key` matching env `TG_EDIT_API_KEY` (if set).
"""
from __future__ import annotations
import logging
import os
import tempfile
from aiohttp import web
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    ChatAdminRequiredError,
)

log = logging.getLogger("tg_send_file")

_API_KEY = os.getenv("TG_EDIT_API_KEY", "")


def _check_auth(request: web.Request) -> bool:
    if not _API_KEY:
        return True
    return request.headers.get("X-API-Key") == _API_KEY


def make_handler(get_client):
    async def handler(request: web.Request):
        if not _check_auth(request):
            log.warning("Unauthorized send-file attempt from %s", request.remote)
            return web.json_response({"error": "unauthorized"}, status=401)

        client: TelegramClient | None = get_client()
        if client is None:
            log.error("Send-file request failed: client not connected")
            return web.json_response({"error": "telegram client not connected"}, status=503)

        # Parse multipart
        try:
            data = await request.post()
        except Exception as e:
            log.warning("Send-file multipart error: %s", e)
            return web.json_response({"error": f"multipart error: {e}"}, status=400)

        try:
            chat_id = int(data.get("chat_id", 0))
        except (TypeError, ValueError):
            log.warning("Send-file missing/invalid chat_id")
            return web.json_response({"error": "missing/invalid chat_id"}, status=400)

        file_field = data.get("file")
        if not file_field or not hasattr(file_field, "file"):
            log.warning("Send-file missing file upload")
            return web.json_response({"error": "missing file upload"}, status=400)

        caption = str(data.get("caption", ""))
        reply_to = data.get("reply_to")
        if reply_to is not None:
            try:
                reply_to = int(reply_to)
            except (TypeError, ValueError):
                reply_to = None
        force_doc = str(data.get("force_doc", "true")).lower() in ("1", "true", "yes")

        # Save uploaded file to temp
        suffix = os.path.splitext(getattr(file_field, "filename", "") or "")[1] or ".bin"
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(file_field.file.read())
                tmp_path = tmp.name
        except Exception as e:
            log.error("Save temp file failed: %s", e)
            return web.json_response({"error": f"save temp file: {e}"}, status=500)

        try:
            log.debug("Send file: chat=%d file=%s caption=%r reply_to=%s force_doc=%s",
                      chat_id, getattr(file_field, "filename", "?"), caption[:60], reply_to, force_doc)
            msg = await client.send_file(
                entity=chat_id,
                file=tmp_path,
                caption=caption,
                reply_to=reply_to,
                force_document=force_doc,
            )
            log.info("Send file OK: chat=%d msg_id=%d", chat_id, msg.id)
            return web.json_response({"ok": True, "id": msg.id, "date": str(msg.date)})
        except FloodWaitError as e:
            log.warning("Send file flood_wait: chat=%d seconds=%s", chat_id, e.seconds)
            return web.json_response({"error": "flood_wait", "seconds": e.seconds}, status=429)
        except ChatAdminRequiredError:
            log.warning("Send file no admin rights: chat=%d", chat_id)
            return web.json_response({"error": "user account lacks send rights"}, status=403)
        except Exception as e:
            log.error("Send file failed: chat=%d error=%s: %s", chat_id, type(e).__name__, e)
            return web.json_response({"error": f"{type(e).__name__}: {e}"}, status=502)
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    return handler
