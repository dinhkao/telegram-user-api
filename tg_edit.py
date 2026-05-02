"""tg_edit.py — POST /api/tg/edit-message.

Edits a Telegram message via the user account (Telethon), so the user-account
acts as the sender for the edit. Useful when bot edits hit rate limits or when
you want the edit to come from a real user/admin account.

Body JSON:
    {
        "chat_id":    int   (required, e.g. -1002138495144),
        "message_id": int   (required),
        "text":       str   (required),
        "parse_mode": "html" | "md" | None  (default: "html"),
        "link_preview": bool (default: False)
    }

Auth: requires header `X-API-Key` matching env `TG_EDIT_API_KEY` (if set).
"""
from __future__ import annotations
import os
from aiohttp import web
from telethon import TelegramClient
from telethon.errors import (
    MessageNotModifiedError,
    FloodWaitError,
    MessageIdInvalidError,
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
            message_id = int(body["message_id"])
            text = body["text"]
        except (KeyError, TypeError, ValueError) as e:
            return web.json_response({"error": f"missing/invalid field: {e}"}, status=400)

        parse_mode = body.get("parse_mode", "html")
        link_preview = bool(body.get("link_preview", False))

        try:
            msg = await client.edit_message(
                entity=chat_id,
                message=message_id,
                text=text,
                parse_mode=parse_mode,
                link_preview=link_preview,
            )
            return web.json_response({"ok": True, "id": msg.id, "edit_date": str(msg.edit_date)})
        except MessageNotModifiedError:
            return web.json_response({"ok": True, "unchanged": True})
        except FloodWaitError as e:
            return web.json_response(
                {"error": "flood_wait", "seconds": e.seconds},
                status=429,
            )
        except MessageIdInvalidError:
            return web.json_response({"error": "message_id invalid or not editable"}, status=404)
        except ChatAdminRequiredError:
            return web.json_response({"error": "user account lacks edit rights in this chat"}, status=403)
        except Exception as e:
            return web.json_response({"error": f"{type(e).__name__}: {e}"}, status=502)

    return handler
