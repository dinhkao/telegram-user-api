"""tg_send.py — POST /api/tg/send-message.

Sends a Telegram message via the user account (Telethon), so the user-account
acts as the sender. Useful when you want replies to come from a real user/admin
account instead of a bot.

Body JSON:
    {
        "chat_id":    int   (required, e.g. -1002124542200),
        "text":       str   (required),
        "parse_mode": "html" | "md" | None  (default: "html"),
        "reply_to":   int   (optional, message ID to reply to),
        "link_preview": bool (default: False)
    }

Auth: requires header `X-API-Key` matching env `TG_EDIT_API_KEY` (if set).
"""
from __future__ import annotations
import os
from aiohttp import web
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    ChatAdminRequiredError,
)


_API_KEY = os.getenv("TG_EDIT_API_KEY", "")


def _check_auth(request: web.Request) -> bool:
    if not _API_KEY:
        return True  # auth disabled
    return request.headers.get("X-API-Key") == _API_KEY


def make_handler(get_client):
    """Returns an aiohttp handler. `get_client` is a zero-arg callable that
    returns the TelegramClient (or None if not connected).
    """

    async def handler(request: web.Request):
        if not _check_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)

        client: TelegramClient | None = get_client()
        if client is None:
            return web.json_response({"error": "telegram client not connected"}, status=503)

        try:
            body = await request.json()
        except Exception as e:
            return web.json_response({"error": f"invalid json: {e}"}, status=400)

        try:
            chat_id = int(body["chat_id"])
            text = body["text"]
        except (KeyError, TypeError, ValueError) as e:
            return web.json_response({"error": f"missing/invalid field: {e}"}, status=400)

        parse_mode = body.get("parse_mode", "html")
        reply_to = body.get("reply_to")
        link_preview = bool(body.get("link_preview", False))

        try:
            msg = await client.send_message(
                entity=chat_id,
                message=text,
                parse_mode=parse_mode,
                reply_to=reply_to,
                link_preview=link_preview,
            )
            return web.json_response({"ok": True, "id": msg.id, "date": str(msg.date)})
        except FloodWaitError as e:
            return web.json_response(
                {"error": "flood_wait", "seconds": e.seconds},
                status=429,
            )
        except ChatAdminRequiredError:
            return web.json_response({"error": "user account lacks send rights in this chat"}, status=403)
        except Exception as e:
            return web.json_response({"error": f"{type(e).__name__}: {e}"}, status=502)

    return handler
