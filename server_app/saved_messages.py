from __future__ import annotations

import json
import logging

from aiohttp import web
from telethon import Button, events
from telethon.tl.types import MessageService

from server_app.ai_backend import ask_ai
from server_app.config import GROUP_ID
from server_app.formatters import sender_info
from server_app.state import recent_messages, ws_clients
from server_app.telegram_helpers import tg_delete_messages, tg_send_message

log = logging.getLogger("server")


async def load_recent_messages(client, limit=100):
    msgs = await client.get_messages("me", limit=limit)
    recent_messages[:] = [{
        "type": "new", "id": msg.id, "date": msg.date.isoformat(), "sender": sender_info(await msg.get_sender()), "text": msg.text[:1000] if msg.text else None, "media": type(msg.media).__name__.replace("MessageMedia", "") if msg.media else None, "reply_to": msg.reply_to_msg_id,
    } for msg in reversed(msgs)]
    log.info("Loaded %d recent messages", len(recent_messages))


async def broadcast(data: dict, persist=True):
    if persist:
        recent_messages.append(data)
        if len(recent_messages) > 500:
            recent_messages.pop(0)
    payload = json.dumps(data, default=str)
    for ws in ws_clients.copy():
        try:
            await ws.send_str(payload)
        except Exception:
            ws_clients.discard(ws)


async def auto_reply_yes(client, chat, text):
    if text and text.strip().lower() != "yes":
        await tg_send_message(chat, "yes", buttons=[[Button.inline("✅ Yes", b"yes"), Button.inline("❌ No", b"no")], [Button.inline("🔄 Maybe", b"maybe")]])


def register_handlers(client):
    @client.on(events.NewMessage(chats="me"))
    async def on_new_message(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        data = {"type": "new", "id": msg.id, "date": msg.date.isoformat(), "sender": sender_info(event.sender), "text": msg.text[:1000] if msg.text else None, "media": type(msg.media).__name__.replace("MessageMedia", "") if msg.media else None, "reply_to": msg.reply_to_msg_id}
        log.info("New: %s: %s", data["sender"]["name"], (msg.text or "[media]")[:80])
        await broadcast(data)
        if msg.text and msg.text.strip().lower() != "yes":
            await auto_reply_yes(client, "me", msg.text)

    @client.on(events.NewMessage(chats=GROUP_ID))
    async def on_group_message(event):
        msg = event.message
        if isinstance(msg, MessageService) or not (msg.text or "").strip() or (msg.text or "").strip().startswith("🤔 Thinking..."):
            return
        status_msg = await tg_send_message(GROUP_ID, "🤔 Thinking...")
        answer = await ask_ai(str(GROUP_ID), msg.text or "")
        await tg_delete_messages(GROUP_ID, [status_msg.id])
        await tg_send_message(GROUP_ID, answer[:4000] + ("..." if len(answer) > 4000 else ""), reply_to=msg.id)

    @client.on(events.MessageEdited(chats="me"))
    async def on_message_edited(event):
        await broadcast({"type": "edit", "id": event.message.id, "date": event.message.date.isoformat(), "text": event.message.text[:1000] if event.message.text else None})

    @client.on(events.MessageDeleted(chats="me"))
    async def on_message_deleted(event):
        await broadcast({"type": "delete", "ids": event.deleted_ids or []})

    @client.on(events.CallbackQuery)
    async def on_callback(event):
        data = event.data.decode()
        sender = await event.get_sender()
        await event.answer(f"You clicked: {data}", alert=False)
        await event.edit(f"yes — {sender_info(sender)['name']} chose **{data.upper()}**")
