from __future__ import annotations

import logging

from aiohttp import web
from telethon import TelegramClient
from telethon.errors import (
    ChatAdminRequiredError,
    FloodWaitError,
    MessageIdInvalidError,
    MessageNotModifiedError,
)

from .common import check_auth

log = logging.getLogger("tg_edit")


def make_handler(get_client):
    async def handler(request: web.Request):
        if not check_auth(request):
            log.warning("Unauthorized edit attempt from %s", request.remote)
            return web.json_response({"error": "unauthorized"}, status=401)
        client: TelegramClient | None = get_client()
        if client is None:
            log.error("Edit request failed: client not connected")
            return web.json_response({"error": "telegram client not connected"}, status=503)
        try:
            body = await request.json()
        except Exception as e:
            log.warning("Edit request invalid JSON: %s", e)
            return web.json_response({"error": f"invalid json: {e}"}, status=400)
        try:
            chat_id = int(body["chat_id"])
            message_id = int(body["message_id"])
            text = body["text"]
        except (KeyError, TypeError, ValueError) as e:
            log.warning("Edit request missing/invalid field: %s", e)
            return web.json_response({"error": f"missing/invalid field: {e}"}, status=400)
        parse_mode = body.get("parse_mode", "html")
        link_preview = bool(body.get("link_preview", False))
        log.debug("Edit msg: chat=%d msg_id=%d text_len=%d parse=%s link_prev=%s", chat_id, message_id, len(text), parse_mode, link_preview)
        try:
            msg = await client.edit_message(
                entity=chat_id,
                message=message_id,
                text=text,
                parse_mode=parse_mode,
                link_preview=link_preview,
            )
            log.info("Edit OK: chat=%d msg_id=%d", chat_id, message_id)
            return web.json_response({"ok": True, "id": msg.id, "edit_date": str(msg.edit_date)})
        except MessageNotModifiedError:
            log.debug("Edit unchanged: chat=%d msg_id=%d", chat_id, message_id)
            return web.json_response({"ok": True, "unchanged": True})
        except FloodWaitError as e:
            log.warning("Edit flood_wait: chat=%d msg_id=%d seconds=%s", chat_id, message_id, e.seconds)
            return web.json_response({"error": "flood_wait", "seconds": e.seconds}, status=429)
        except MessageIdInvalidError:
            log.warning("Edit invalid msg_id: chat=%d msg_id=%d", chat_id, message_id)
            return web.json_response({"error": "message_id invalid or not editable"}, status=404)
        except ChatAdminRequiredError:
            log.warning("Edit no admin rights: chat=%d msg_id=%d", chat_id, message_id)
            return web.json_response({"error": "user account lacks edit rights in this chat"}, status=403)
        except Exception as e:
            log.error("Edit failed: chat=%d msg_id=%d error=%s: %s", chat_id, message_id, type(e).__name__, e)
            return web.json_response({"error": f"{type(e).__name__}: {e}"}, status=502)
    return handler
