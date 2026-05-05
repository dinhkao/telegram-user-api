"""
Telegram User API - Real-time Chat Listener
Listens to new messages, edits, and deletions in a target chat.
"""
import asyncio
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import (
    MessageService,
    MessageEntityTextUrl,
    MessageEntityMention,
)

from utils.logger import configure_logging

load_dotenv()
configure_logging()
log = logging.getLogger("listener")

# ─── Configuration ────────────────────────────────────────────────────────────
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
PHONE = os.getenv("PHONE", "")
TARGET_CHAT = os.getenv("TARGET_CHAT", "")

if not all([API_ID, API_HASH, PHONE, TARGET_CHAT]):
    log.error("Missing config! Copy .env.example -> .env and fill in your credentials.")
    sys.exit(1)

client = TelegramClient("user_session", API_ID, API_HASH)


# ─── Helpers ───────────────────────────────────────────────────────────────────
def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def fmt_sender(event) -> str:
    """Format sender name nicely."""
    sender = event.sender
    if not sender:
        return "Unknown"

    if hasattr(sender, "title"):
        name = sender.title
        username = f" (@{sender.username})" if getattr(sender, "username", None) else ""
        return f"{name}{username} [ID:{sender.id}]"

    name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
    username = f" (@{sender.username})" if getattr(sender, "username", None) else ""
    return f"{name}{username} [ID:{sender.id}]"


# ─── Event Handlers ───────────────────────────────────────────────────────────

@client.on(events.NewMessage(chats=TARGET_CHAT))
async def on_new_message(event):
    """Handle new incoming messages."""
    msg = event.message

    if isinstance(msg, MessageService):
        return

    sender = fmt_sender(event)
    log.info("New msg id=%d from %s reply_to=%s", msg.id, sender, msg.reply_to_msg_id or '-')

    if msg.text:
        text = msg.text[:500] + ("..." if len(msg.text) > 500 else "")
        log.debug("Text: %s", text)

    if msg.media:
        media_type = type(msg.media).__name__.replace("MessageMedia", "")
        log.debug("Media: %s", media_type)

    if msg.fwd_from:
        log.debug("Forwarded from: %s", msg.fwd_from.from_name or msg.fwd_from.from_id or 'Unknown')


@client.on(events.MessageEdited(chats=TARGET_CHAT))
async def on_message_edited(event):
    """Handle edited messages."""
    msg = event.message
    sender = fmt_sender(event)
    log.info("Edited msg id=%d from %s", msg.id, sender)

    if msg.text:
        text = msg.text[:500] + ("..." if len(msg.text) > 500 else "")
        log.debug("New text: %s", text)


@client.on(events.MessageDeleted(chats=TARGET_CHAT))
async def on_message_deleted(event):
    """Handle deleted messages. Only IDs are available (Telegram doesn't expose content)."""
    deleted_ids = event.deleted_ids or []
    log.info("Deleted %d message(s) ids=%s", len(deleted_ids), deleted_ids)


# ─── Main ──────────────────────────────────────────────────────────────────────
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

    log.info("Listening for new messages, edits, and deletions... (Ctrl+C to stop)")
    log.info("─" * 60)

    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Disconnected.")
