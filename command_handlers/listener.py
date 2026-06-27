from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import MessageEntityMention, MessageEntityTextUrl, MessageService

from utils.logger import configure_logging

load_dotenv()
configure_logging()
log = logging.getLogger("listener")
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
PHONE = os.getenv("PHONE", "")
TARGET_CHAT = os.getenv("TARGET_CHAT", "")
client = TelegramClient("user_session", API_ID, API_HASH)


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _fmt_sender(event) -> str:
    sender = event.sender
    if not sender:
        return "Unknown"
    if hasattr(sender, "title"):
        return f"{sender.title}{f' (@{sender.username})' if getattr(sender, 'username', None) else ''} [ID:{sender.id}]"
    name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
    return f"{name}{f' (@{sender.username})' if getattr(sender, 'username', None) else ''} [ID:{sender.id}]"


def register_listener_handlers(client):
    @client.on(events.NewMessage(chats=TARGET_CHAT))
    async def on_new_message(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        log.info("New msg id=%d from %s reply_to=%s", msg.id, _fmt_sender(event), msg.reply_to_msg_id or "-")
        if msg.text:
            log.debug("Text: %s", msg.text[:500] + ("..." if len(msg.text) > 500 else ""))
        if msg.media:
            log.debug("Media: %s", type(msg.media).__name__.replace("MessageMedia", ""))
        if msg.fwd_from:
            log.debug("Forwarded from: %s", msg.fwd_from.from_name or msg.fwd_from.from_id or "Unknown")

    @client.on(events.MessageEdited(chats=TARGET_CHAT))
    async def on_message_edited(event):
        msg = event.message
        log.info("Edited msg id=%d from %s", msg.id, _fmt_sender(event))
        if msg.text:
            log.debug("New text: %s", msg.text[:500] + ("..." if len(msg.text) > 500 else ""))

    @client.on(events.MessageDeleted(chats=TARGET_CHAT))
    async def on_message_deleted(event):
        log.info("Deleted %d message(s) ids=%s", len(event.deleted_ids or []), event.deleted_ids or [])


async def main():
    log.info("Authenticating...")
    await client.start(phone=PHONE)
    me = await client.get_me()
    log.info("Logged in as: %s", me.first_name)
    try:
        entity = await client.get_entity(TARGET_CHAT)
        log.info("Listening to: %s (ID: %s)", entity.title or entity.first_name, entity.id)
    except Exception as e:
        log.error("Cannot find chat '%s': %s", TARGET_CHAT, e)
        sys.exit(1)
    register_listener_handlers(client)
    log.info("Listening for new messages, edits, and deletions... (Ctrl+C to stop)")
    log.info("─" * 60)
    await client.run_until_disconnected()
