"""
server.py — Real-time Saved Messages monitor with WebSocket push.
Starts a Telethon listener on "Saved Messages" + aiohttp web server.
Clients connect via WebSocket at ws://localhost:8080/ws
"""
import asyncio
import json
import os
import ssl
import subprocess
import sys
from datetime import datetime
import http.client
import unicodedata

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
_client: TelegramClient | None = None


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


# ─── Vietnamese accent normalization ──────────────────────────────────────────
def vn_normalize(text: str) -> str:
    """Remove Vietnamese diacritics for accent-insensitive search.
    'Xin chào' -> 'xin chao', 'Đường' -> 'duong'
    """
    if not text:
        return ""
    # đ/Đ don't decompose via NFD — handle them first
    text = text.replace('đ', 'd').replace('Đ', 'd')
    nfd = unicodedata.normalize('NFD', text)
    return ''.join(c for c in nfd if not unicodedata.combining(c)).lower()


# ─── AI Backend ────────────────────────────────────────────────────────────────
# "pi" = use pi CLI (has tools: bash, read, write, web search, etc.)
# "fireworks" = use direct Fireworks API (chat only, no tools)
AI_BACKEND = os.getenv("AI_BACKEND", "pi")

FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY", "")
PI_MODEL = os.getenv("PI_MODEL", "fireworks/accounts/fireworks/routers/kimi-k2p5-turbo")

# Per-chat conversation history (used by fireworks backend)
import pathlib
PI_SESSIONS_DIR = pathlib.Path(os.getenv("PI_SESSIONS_DIR", os.path.expanduser("~/.pi/agent/tg-sessions")))
PI_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


async def ask_pi(chat_id: str, question: str) -> str:
    """Use pi CLI with --session for tool capabilities (bash, read, write, search)."""
    loop = asyncio.get_running_loop()
    safe_id = str(chat_id).replace("/", "_").replace(":", "_").lstrip("-")
    session_path = PI_SESSIONS_DIR / f"{safe_id}.jsonl"

    cmd = ["pi", "-p", "--model", PI_MODEL, "--session", str(session_path), question]
    env = os.environ.copy()
    if FIREWORKS_API_KEY:
        env["FIREWORKS_API_KEY"] = FIREWORKS_API_KEY

    try:
        proc = await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=180),
        )
        output = (proc.stdout or "").strip()
        if not output and proc.stderr:
            output = f"Error: {proc.stderr.strip()[:500]}"
        return output or "(empty response)"
    except subprocess.TimeoutExpired:
        return "Timeout: pi took too long."
    except Exception as e:
        return f"Error running pi: {e}"


async def ask_ai(chat_id: str, question: str) -> str:
    """Route to pi CLI (with tools) or direct Fireworks API."""
    if AI_BACKEND == "pi":
        return await ask_pi(chat_id, question)
    else:
        return await _ask_fireworks(chat_id, question)


# ─── Direct Fireworks API (optional, no tools) ────────────────────────────────
FIREWORKS_MODEL = os.getenv("FIREWORKS_MODEL", "accounts/fireworks/routers/kimi-k2p5-turbo")
if FIREWORKS_MODEL.startswith("fireworks/"):
    FIREWORKS_MODEL = FIREWORKS_MODEL[len("fireworks/"):]
SYSTEM_PROMPT = "You are a helpful assistant in a Telegram group chat. Keep answers concise and clear."
chat_histories: dict[str, list[dict]] = {}
MAX_HISTORY = 20


def _ask_fireworks_sync(messages: list[dict]) -> str:
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection("api.fireworks.ai", context=ctx, timeout=120)
    payload = json.dumps({"model": FIREWORKS_MODEL, "messages": messages, "max_tokens": 1024})
    conn.request("POST", "/inference/v1/chat/completions", payload, {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    r = conn.getresponse()
    body = json.loads(r.read())
    conn.close()
    content = body["choices"][0]["message"]["content"].strip()
    if "</thinking>" in content:
        content = content.split("</thinking>")[-1].strip()
    return content


async def _ask_fireworks(chat_id: str, question: str) -> str:
    loop = asyncio.get_running_loop()
    history = chat_histories.setdefault(str(chat_id), [])
    history.append({"role": "user", "content": question})
    if len(history) > MAX_HISTORY * 2:
        history[:] = history[-(MAX_HISTORY * 2):]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    try:
        answer = await loop.run_in_executor(None, _ask_fireworks_sync, messages)
        history.append({"role": "assistant", "content": answer})
        return answer or "(empty response)"
    except Exception as e:
        history.pop()
        return f"Error: {e}"


GROUP_ID = int(os.getenv("GROUP_ID", 0))


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
            answer = await ask_ai(str(GROUP_ID), text)
            await client.delete_messages(GROUP_ID, [status_msg.id])
            await client.send_message(
                GROUP_ID,
                answer[:4000] + ("..." if len(answer) > 4000 else ""),
                reply_to=msg.id,
            )
            print(f"🤖 [{datetime.now():%H:%M:%S}] Replied with Fireworks answer ({len(answer)} chars)")

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


# ─── Search endpoint ──────────────────────────────────────────────────────────
async def search_handler(request: web.Request):
    """Search saved messages with Vietnamese no-accent matching.
    GET /api/search?q=...&offset=N
    If no results in memory, fetches next 100 from Telegram.
    Returns {results, searched, has_more, next_offset}
    """
    q = request.query.get("q", "").strip()
    if not q:
        return web.json_response({"results": [], "searched": 0, "has_more": False, "next_offset": 0})

    if _client is None:
        return web.json_response({"error": "Telegram client not connected yet"}, status=503)

    normalized_q = vn_normalize(q)
    results: list[dict] = []

    # 1. Search in-memory recent_messages (fast path)
    for msg in recent_messages:
        text = msg.get("text") or ""
        if normalized_q in vn_normalize(text):
            results.append(msg)

    total_searched = len(recent_messages)

    # 2. If no results, fetch one batch from Telegram
    offset_id = int(request.query.get("offset", "0"))
    if not offset_id and recent_messages:
        offset_id = recent_messages[0]["id"]  # oldest cached msg

    has_more = False
    next_offset = 0

    if not results and offset_id > 0:
        try:
            batch = await _client.get_messages("me", limit=100, offset_id=offset_id)
        except Exception as e:
            err = str(e)
            if "FloodWait" in err or "FLOOD_WAIT" in err:
                return web.json_response({
                    "error": "Telegram rate limit — wait a moment and try again",
                    "searched": total_searched,
                }, status=429)
            return web.json_response({"error": err, "searched": total_searched}, status=500)

        if batch:
            total_searched += len(batch)
            for msg in batch:
                text = msg.text or ""
                if normalized_q in vn_normalize(text):
                    s = await msg.get_sender()
                    results.append({
                        "type": "new",
                        "id": msg.id,
                        "date": msg.date.isoformat(),
                        "sender": sender_info(s),
                        "text": msg.text[:1000] if msg.text else None,
                        "media": type(msg.media).__name__.replace("MessageMedia", "") if msg.media else None,
                        "reply_to": msg.reply_to_msg_id,
                    })

            if not results:
                next_offset = batch[-1].id
                has_more = True

    return web.json_response({
        "results": results,
        "searched": total_searched,
        "has_more": has_more,
        "next_offset": next_offset,
    })


# ─── Main ──────────────────────────────────────────────────────────────────────
async def main():
    global _client

    # Start Telethon
    client = TelegramClient("user_session", API_ID, API_HASH)
    _client = client
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
    app.router.add_get("/api/search", search_handler)
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
