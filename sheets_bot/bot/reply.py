"""Reply/error helpers (port of getErrorHint / handleBotError / send)."""

from __future__ import annotations

import logging

log = logging.getLogger("sheets_bot.bot")


def error_hint(err) -> str:
    if not err:
        return ""
    msg = str(getattr(err, "message", None) or err)
    if "ECONNREFUSED" in msg or "ENOTFOUND" in msg:
        return " (lỗi kết nối mạng)"
    if "401" in msg or "403" in msg or "PERMISSION_DENIED" in msg:
        return " (không có quyền truy cập sheet)"
    if "404" in msg or "NOT_FOUND" in msg:
        return " (sheet không tồn tại)"
    if "QUOTA_EXCEEDED" in msg:
        return " (vượt quota Google API)"
    return ""


async def send(client, chat_id, text, thread_id=None):
    kwargs = {}
    if thread_id:
        kwargs["reply_to"] = thread_id
    await client.send_message(chat_id, text, **kwargs)


async def handle_error(client, chat_id, user_msg, err, thread_id=None):
    hint = error_hint(err)
    log.error("%s: %s", user_msg, err)
    await send(client, chat_id, f"{user_msg}{hint}.", thread_id)
