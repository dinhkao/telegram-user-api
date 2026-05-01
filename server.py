"""
server.py — Real-time Saved Messages monitor with WebSocket push.
Starts a Telethon listener on "Saved Messages" + aiohttp web server.
Clients connect via WebSocket at ws://localhost:8080/ws
"""
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime

from aiohttp import web
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button
from telethon.tl.types import MessageService

load_dotenv()

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
PHONE = os.getenv("PHONE", "")
PORT = int(os.getenv("PORT", 8080))

if not all([API_ID, API_HASH, PHONE]):
    print("❌ Missing .env config!")
    sys.exit(1)

# ─── WebSocket broadcast ──────────────────────────────────────────────────────
ws_clients: set[web.WebSocketResponse] = set()
recent_messages: list[dict] = []


async def load_recent_messages(client: TelegramClient, limit=100):
    """Fetch recent messages and store them for new clients."""
    global recent_messages
    msgs = await client.get_messages("me", limit=limit)
    recent_messages = []
    for msg in reversed(msgs):
        s = await msg.get_sender()
        data = {
            "type": "new",
            "id": msg.id,
            "date": msg.date.isoformat(),
            "sender": sender_info(s),
            "text": msg.text[:1000] if msg.text else None,
            "media": type(msg.media).__name__.replace("MessageMedia", "") if msg.media else None,
            "reply_to": msg.reply_to_msg_id,
        }
        recent_messages.append(data)
    print(f"📋 Loaded {len(recent_messages)} recent messages")


async def broadcast(data: dict, persist=True):
    """Send JSON to all connected WebSocket clients."""
    if persist:
        recent_messages.append(data)
        # Keep only last 500
        if len(recent_messages) > 500:
            recent_messages.pop(0)

    payload = json.dumps(data, default=str)
    for ws in ws_clients.copy():
        try:
            await ws.send_str(payload)
        except Exception:
            ws_clients.discard(ws)


# ─── Sender formatting ────────────────────────────────────────────────────────
def sender_info(sender) -> dict:
    if not sender:
        return {"name": "Unknown", "id": 0}
    if hasattr(sender, "title"):
        name = sender.title
        if getattr(sender, "username", None):
            name += f" (@{sender.username})"
        return {"name": name, "id": sender.id, "is_channel": True}
    name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
    if getattr(sender, "username", None):
        name += f" (@{sender.username})"
    return {"name": name, "id": sender.id, "is_channel": False}


# ─── Telethon event handlers ──────────────────────────────────────────────────
GROUP_ID = int(os.getenv("GROUP_ID", 0))


PI_MODEL = os.getenv("PI_MODEL", "fireworks/accounts/fireworks/routers/kimi-k2p5-turbo")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY", "")


async def ask_pi(question: str) -> str:
    """Run pi -p in a subprocess and return the output."""
    loop = asyncio.get_running_loop()
    cmd = [
        "pi", "-p",
        "--model", PI_MODEL,
        question,
    ]
    env = os.environ.copy()
    if FIREWORKS_API_KEY:
        env["FIREWORKS_API_KEY"] = FIREWORKS_API_KEY

    try:
        proc = await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120),
        )
        output = (proc.stdout or "").strip()
        if not output and proc.stderr:
            output = f"Error: {proc.stderr.strip()[:500]}"
        return output or "(empty response)"
    except subprocess.TimeoutExpired:
        return "Timeout: pi took too long to respond."
    except Exception as e:
        return f"Error running pi: {e}"


async def auto_reply_yes(client, chat, text):
    """Reply 'yes' to a chat with inline keyboard buttons (Saved Messages only)."""
    if text and text.strip().lower() != "yes":
        buttons = [
            [Button.inline("✅ Yes", b"yes"), Button.inline("❌ No", b"no")],
            [Button.inline("🔄 Maybe", b"maybe")],
        ]
        await client.send_message(chat, "yes", buttons=buttons)
        label = getattr(chat, "title", None) if not isinstance(chat, str) else chat
        if label is None:
            label = getattr(chat, "first_name", str(chat))
        print(f"🤖 [{datetime.now():%H:%M:%S}] Auto-replied 'yes' to {label}")


def register_handlers(client: TelegramClient):
    # ── Saved Messages ────────────────────────────────────────────────────────
    @client.on(events.NewMessage(chats="me"))
    async def on_new_message(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        sender = sender_info(event.sender)

        data = {
            "type": "new",
            "id": msg.id,
            "date": msg.date.isoformat(),
            "sender": sender,
            "text": msg.text[:1000] if msg.text else None,
            "media": type(msg.media).__name__.replace("MessageMedia", "") if msg.media else None,
            "reply_to": msg.reply_to_msg_id,
        }
        print(f"🆕 [{datetime.now():%H:%M:%S}] {sender['name']}: { (msg.text or '[media]')[:80]}")
        await broadcast(data)

        # Auto-reply with inline keyboard (avoid infinite loop)
        if msg.text and msg.text.strip().lower() != "yes":
            await auto_reply_yes(client, "me", msg.text)

    # ── Group chat ────────────────────────────────────────────────────────────
    if GROUP_ID:
        @client.on(events.NewMessage(chats=GROUP_ID))
        async def on_group_message(event):
            msg = event.message
            if isinstance(msg, MessageService):
                return

            # Skip service messages
            if isinstance(msg, MessageService):
                return

            text = msg.text or ""

            # Skip the bot's own "Thinking..." placeholders (prevent self-loop)
            if text.strip().startswith("🤔 Thinking..."):
                return

            sender = sender_info(event.sender)
            print(f"💬 [{datetime.now():%H:%M:%S}] Group - {sender['name']}: {text[:80]}")

            if not text.strip():
                return

            # Send "thinking..." placeholder
            status_msg = await client.send_message(GROUP_ID, "🤔 Thinking...")

            # Ask pi and reply
            answer = await ask_pi(text)
            await client.delete_messages(GROUP_ID, [status_msg.id])
            await client.send_message(
                GROUP_ID,
                answer[:4000] + ("..." if len(answer) > 4000 else ""),
                reply_to=msg.id,
            )
            print(f"🤖 [{datetime.now():%H:%M:%S}] Replied with pi answer ({len(answer)} chars)")

    @client.on(events.MessageEdited(chats="me"))
    async def on_message_edited(event):
        msg = event.message
        data = {
            "type": "edit",
            "id": msg.id,
            "date": msg.date.isoformat(),
            "text": msg.text[:1000] if msg.text else None,
        }
        print(f"✏️  [{datetime.now():%H:%M:%S}] Edited msg {msg.id}")
        await broadcast(data)

    @client.on(events.MessageDeleted(chats="me"))
    async def on_message_deleted(event):
        data = {
            "type": "delete",
            "ids": event.deleted_ids or [],
        }
        print(f"🗑️  [{datetime.now():%H:%M:%S}] Deleted: {data['ids']}")
        await broadcast(data)

    # ── Inline keyboard callback handler ──────────────────────────────────────
    @client.on(events.CallbackQuery)
    async def on_callback(event):
        data = event.data.decode()
        sender = await event.get_sender()
        sname = sender_info(sender)["name"]
        await event.answer(f"You clicked: {data}", alert=False)
        print(f"🔘 [{datetime.now():%H:%M:%S}] {sname} clicked: {data}")
        await event.edit(f"yes — {sname} chose **{data.upper()}**")


# ─── HTTP / WebSocket routes ──────────────────────────────────────────────────
async def index_handler(request: web.Request):
    return web.FileResponse("static/index.html")


async def websocket_handler(request: web.Request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    ws_clients.add(ws)
    print(f"🔌 Client connected ({len(ws_clients)} total)")

    # Send recent message history
    history = {"type": "history", "messages": recent_messages}
    await ws.send_str(json.dumps(history, default=str))

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                if msg.data == "history":
                    history = {"type": "history", "messages": recent_messages}
                    await ws.send_str(json.dumps(history, default=str))
            elif msg.type == web.WSMsgType.ERROR:
                print(f"WS error: {ws.exception()}")
    finally:
        ws_clients.discard(ws)
        print(f"🔌 Client disconnected ({len(ws_clients)} total)")
    return ws


# ─── Main ──────────────────────────────────────────────────────────────────────
async def main():
    # Start Telethon
    client = TelegramClient("user_session", API_ID, API_HASH)
    await client.start(phone=PHONE)
    me = await client.get_me()
    print(f"✅ Logged in as {me.first_name}")
    print(f"👂 Listening to Saved Messages...")

    # Load recent message history
    await load_recent_messages(client, limit=100)
    register_handlers(client)

    # Start aiohttp
    app = web.Application()
    app.router.add_get("/", index_handler)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_static("/static/", "static")

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Web server: http://localhost:{PORT}")
    print("─" * 50)

    # Run both forever
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Shutting down.")
