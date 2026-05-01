"""
Telegram User API - Real-time Chat Listener
Listens to new messages, edits, and deletions in a target chat.
"""
import asyncio
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

load_dotenv()

# ─── Configuration ────────────────────────────────────────────────────────────
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
PHONE = os.getenv("PHONE", "")
TARGET_CHAT = os.getenv("TARGET_CHAT", "")

if not all([API_ID, API_HASH, PHONE, TARGET_CHAT]):
    print("❌ Missing config! Copy .env.example → .env and fill in your credentials.")
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

    # Channel / group sender
    if hasattr(sender, "title"):
        name = sender.title
        username = f" (@{sender.username})" if getattr(sender, "username", None) else ""
        return f"{name}{username} [ID:{sender.id}]"

    # User sender
    name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
    username = f" (@{sender.username})" if getattr(sender, "username", None) else ""
    return f"{name}{username} [ID:{sender.id}]"


# ─── Event Handlers ───────────────────────────────────────────────────────────

@client.on(events.NewMessage(chats=TARGET_CHAT))
async def on_new_message(event):
    """Handle new incoming messages."""
    msg = event.message

    # Skip service messages (e.g., "user joined the group")
    if isinstance(msg, MessageService):
        return

    print(f"\n🆕 [{now()}] NEW MESSAGE from {fmt_sender(event)}")
    print(f"   ID: {msg.id}  |  Reply to: {msg.reply_to_msg_id or '—'}")

    # Print text content
    if msg.text:
        text = msg.text[:500] + ("..." if len(msg.text) > 500 else "")
        print(f"   Text: {text}")

    # Media
    if msg.media:
        media_type = type(msg.media).__name__.replace("MessageMedia", "")
        print(f"   📎 Media: {media_type}")

    # Forwards
    if msg.fwd_from:
        print(f"   🔄 Forwarded from: {msg.fwd_from.from_name or msg.fwd_from.from_id or 'Unknown'}")


@client.on(events.MessageEdited(chats=TARGET_CHAT))
async def on_message_edited(event):
    """Handle edited messages."""
    msg = event.message

    print(f"\n✏️  [{now()}] EDITED MESSAGE from {fmt_sender(event)}")
    print(f"   ID: {msg.id}")

    if msg.text:
        text = msg.text[:500] + ("..." if len(msg.text) > 500 else "")
        print(f"   New text: {text}")


@client.on(events.MessageDeleted(chats=TARGET_CHAT))
async def on_message_deleted(event):
    """Handle deleted messages. Only IDs are available (Telegram doesn't expose content)."""
    deleted_ids = event.deleted_ids or []
    print(f"\n🗑️  [{now()}] DELETED MESSAGES — {len(deleted_ids)} message(s)")
    print(f"   IDs: {deleted_ids}")


# ─── Main ──────────────────────────────────────────────────────────────────────
async def main():
    print("🔐 Authenticating...")
    await client.start(phone=PHONE)
    print(f"✅ Logged in as: { (await client.get_me()).first_name }")

    # Resolve target chat
    try:
        entity = await client.get_entity(TARGET_CHAT)
        print(f"📌 Listening to: {entity.title or entity.first_name} (ID: {entity.id})")
    except Exception as e:
        print(f"❌ Cannot find chat '{TARGET_CHAT}': {e}")
        sys.exit(1)

    print("👂 Listening for new messages, edits, and deletions... (Ctrl+C to stop)\n")
    print("─" * 60)

    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Disconnected.")
