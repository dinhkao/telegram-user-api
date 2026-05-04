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
import time
import unicodedata
from datetime import datetime
import http.client

from aiohttp import web
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button
from telethon.tl.types import MessageService

from donhang_db import DonHangDB
from donhang_indexer import backfill, register_live_handlers, fill_gap_to_newest
from what_data import register_what_data_handler

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
from vn import vn_normalize  # noqa: E402


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
SEARCH_BATCH = 50  # results per SearchRequest page (like official apps)
SEARCH_MAX_DEEP = 5000  # max messages to deep-scan in fallback

RESULT_CACHE: dict[str, list[dict]] = {}  # query -> results cache
RESULT_CACHE_TTL_SEC = 30  # cache hits expire after 30s


async def _msg_to_dict(msg) -> dict:
    s = await msg.get_sender()
    return {
        "type": "new",
        "id": msg.id,
        "date": msg.date.isoformat(),
        "sender": sender_info(s),
        "text": msg.text[:1000] if msg.text else None,
        "media": type(msg.media).__name__.replace("MessageMedia", "") if msg.media else None,
        "reply_to": msg.reply_to_msg_id,
    }


async def _server_search(query: str, offset_id: int = 0) -> tuple[list[dict], bool, int]:
    """Pass 1: Telegram server-side indexed search via get_messages(search=...).
    Returns (results, has_more, next_offset_id).
    """
    try:
        msgs = await _client.get_messages(
            "me",
            search=query,
            limit=SEARCH_BATCH,
            offset_id=offset_id,
        )
    except Exception as e:
        err = str(e)
        if "FLOOD_WAIT" in err.upper():
            raise
        print(f"[search] Server search error: {e}")
        return [], False, 0

    if not msgs:
        return [], False, 0

    if not isinstance(msgs, list):
        msgs = [msgs] if msgs else []

    results = []
    normalized_q = vn_normalize(query)
    for msg in msgs:
        text = msg.text or ""
        # Telegram server search is fuzzy — filter locally to ensure the query
        # actually appears in the text (accent-insensitive)
        if text and normalized_q in vn_normalize(text):
            results.append({
                "type": "new",
                "id": msg.id,
                "date": msg.date.isoformat(),
                "sender": {"name": "Saved Messages", "id": 0},
                "text": text[:1000],
                "media": type(msg.media).__name__.replace("MessageMedia", "") if msg.media else None,
                "reply_to": msg.reply_to_msg_id,
            })

    has_more = len(msgs) >= SEARCH_BATCH  # more on server, even if filtered here
    next_offset = msgs[-1].id if msgs else 0

    return results, has_more, next_offset


async def _deep_search(query: str, offset_id: int = 0) -> tuple[list[dict], bool, int, int]:
    """Pass 2: Local scan with vn_normalize for accent-insensitive matching.
    Returns (results, has_more, next_offset_id, total_scanned).
    """
    normalized_q = vn_normalize(query)
    results = []
    total_scanned = 0
    has_more = False
    next_offset = 0

    # First search in-memory recent_messages
    for msg in recent_messages:
        total_scanned += 1
        text = msg.get("text") or ""
        if normalized_q in vn_normalize(text):
            results.append(msg)

    if results:
        return results, False, 0, total_scanned

    # Fetch from Telegram in batches
    fetch_offset = offset_id
    if not fetch_offset and recent_messages:
        fetch_offset = recent_messages[0]["id"]  # oldest cached

    while not results and total_scanned < SEARCH_MAX_DEEP:
        try:
            batch = await _client.get_messages("me", limit=100, offset_id=fetch_offset)
        except Exception as e:
            err = str(e)
            if "FLOOD_WAIT" in err.upper():
                raise
            print(f"[search] Deep scan fetch error: {e}")
            break

        if not batch:
            break

        total_scanned += len(batch)
        for msg in batch:
            text = msg.message or ""
            if normalized_q in vn_normalize(text):
                results.append({
                    "type": "new",
                    "id": msg.id,
                    "date": msg.date.isoformat(),
                    "sender": {"name": "Saved Messages", "id": 0},
                    "text": msg.message[:1000] if msg.message else None,
                    "media": type(msg.media).__name__.replace("MessageMedia", "") if msg.media else None,
                    "reply_to": msg.reply_to_msg_id,
                })

        if not results and total_scanned < SEARCH_MAX_DEEP:
            fetch_offset = batch[-1].id
        else:
            next_offset = batch[-1].id
            has_more = total_scanned < SEARCH_MAX_DEEP and not results
            break

    return results, has_more, next_offset, total_scanned


async def search_handler(request: web.Request):
    """Hybrid search: Telegram server index (fast) + local vn_normalize fallback.
    GET /api/search?q=...&offset=N&mode=server|deep
    """
    q = request.query.get("q", "").strip()
    if not q:
        return web.json_response({"results": [], "searched": 0, "has_more": False, "next_offset": 0, "mode": None})

    if _client is None:
        return web.json_response({"error": "Telegram client not connected yet"}, status=503)

    offset_id = int(request.query.get("offset", "0"))
    mode = request.query.get("mode", "auto")  # "auto", "server", "deep"

    # Cache check
    cache_key = f"{q}:{offset_id}:{mode}"
    now = time.monotonic()
    cached = RESULT_CACHE.get(cache_key)
    if cached and (now - cached["ts"]) < RESULT_CACHE_TTL_SEC:
        return web.json_response(cached["data"])

    results = []
    has_more = False
    next_offset = 0
    total_searched = 0
    used_mode = None

    # ── Pass 1: Server search (instant indexed lookup) ─────────────────
    if mode in ("auto", "server"):
        try:
            results, has_more, next_offset = await _server_search(q, offset_id)
            used_mode = "server"
            total_searched = len(results)
        except Exception as e:
            err = str(e)
            if "FLOOD_WAIT" in err.upper():
                return web.json_response({
                    "error": "Telegram rate limit — wait a moment and try again",
                }, status=429)

    # ── Pass 2: Local deep scan (no-accent Vietnamese fallback) ────────
    if not results and mode in ("auto", "deep"):
        print(f"[search] Server returned 0 results for '{q}', starting deep scan...")
        try:
            results, has_more, next_offset, total_searched = await _deep_search(q, offset_id)
            used_mode = "deep"
        except Exception as e:
            err = str(e)
            if "FLOOD_WAIT" in err.upper():
                return web.json_response({
                    "error": "Telegram rate limit — deep scan paused. Try again in a moment.",
                }, status=429)
            print(f"[search] Deep search error: {e}")

    data = {
        "results": results,
        "searched": total_searched,
        "has_more": has_more,
        "next_offset": next_offset,
        "mode": used_mode,
    }

    # Cache it
    RESULT_CACHE[cache_key] = {"data": data, "ts": now}
    # Purge old entries
    stale = [k for k, v in RESULT_CACHE.items() if now - v["ts"] > RESULT_CACHE_TTL_SEC]
    for k in stale:
        del RESULT_CACHE[k]

    return web.json_response(data)


# ─── #don_hang channel search ─────────────────────────────────────────────────
DON_HANG_CHAT_ID = -1002138495144  # TARGET_CHAT from .env as full MTProto ID
DON_HANG_QUERY = "#don_hang"
DON_HANG_BATCH = 50
DON_HANG_DB_PATH = os.getenv("DONHANG_DB", "donhang.db")

_donhang_db: DonHangDB | None = None


async def donhang_handler(request: web.Request):
    """DB-backed search for #don_hang in TARGET_CHAT.
    GET /api/donhang?offset=N&q=text&mode=db|live

    - mode=db (default): Read from local SQLite cache (instant).
      Supports `q` for FTS5 text search (diacritic-insensitive).
    - mode=live: Bypass cache, scan Telegram directly (legacy local scan).
    """
    if _client is None:
        return web.json_response({"error": "Telegram client not connected yet"}, status=503)

    offset_id = int(request.query.get("offset", "0"))
    q = request.query.get("q", "").strip()
    mode = request.query.get("mode", "db")

    if mode == "live":
        return await _donhang_live(offset_id)
    if mode == "server":
        return await _donhang_server(offset_id)

    # DB mode
    if _donhang_db is None:
        return web.json_response({"error": "DB not initialized"}, status=503)

    rows = _donhang_db.search(q, offset_id=offset_id, limit=DON_HANG_BATCH) if q \
        else _donhang_db.page(offset_id=offset_id, limit=DON_HANG_BATCH)

    results = [{
        "id": r["id"],
        "date": r["date"],
        "text": (r["text"] or "")[:2000],
        "media": r["media"],
        "reply_to": r["reply_to"],
    } for r in rows]

    return web.json_response({
        "results": results,
        "has_more": len(rows) >= DON_HANG_BATCH,
        "next_offset": rows[-1]["id"] if rows else 0,
        "mode": "db",
        "query": q,
    })


async def donhang_stats_handler(request: web.Request):
    if _donhang_db is None:
        return web.json_response({"error": "DB not initialized"}, status=503)
    return web.json_response(_donhang_db.stats())


async def _donhang_server(offset_id: int):
    """Telegram server-side hashtag index. Fast but misses edited messages."""
    try:
        msgs = await _client.get_messages(
            DON_HANG_CHAT_ID, search=DON_HANG_QUERY,
            limit=DON_HANG_BATCH, offset_id=offset_id,
        )
    except Exception as e:
        if "FLOOD_WAIT" in str(e).upper():
            return web.json_response({"error": "Telegram rate limit"}, status=429)
        return web.json_response({"error": str(e)}, status=500)
    if not msgs:
        return web.json_response({"results": [], "has_more": False, "next_offset": 0, "mode": "server"})
    if not isinstance(msgs, list):
        msgs = [msgs]
    results = [{
        "id": m.id,
        "date": m.date.isoformat() if m.date else None,
        "text": (m.text or "")[:2000],
    } for m in msgs if (m.text or "")]
    return web.json_response({
        "results": results,
        "has_more": len(msgs) >= DON_HANG_BATCH,
        "next_offset": msgs[-1].id if msgs else 0,
        "mode": "server",
    })


async def _donhang_live(offset_id: int):
    """Legacy: live scan via iter_messages (bypasses DB)."""
    results = []
    scanned = 0
    last_id = offset_id
    try:
        kwargs = {"limit": 500}
        if offset_id:
            kwargs["offset_id"] = offset_id
        async for msg in _client.iter_messages(DON_HANG_CHAT_ID, **kwargs):
            scanned += 1
            last_id = msg.id
            text = msg.text or ""
            if DON_HANG_QUERY in text:
                results.append({
                    "id": msg.id,
                    "date": msg.date.isoformat() if msg.date else None,
                    "text": text[:2000],
                    "media": type(msg.media).__name__.replace("MessageMedia", "") if msg.media else None,
                    "reply_to": msg.reply_to_msg_id,
                })
                if len(results) >= DON_HANG_BATCH:
                    break
    except Exception as e:
        err = str(e)
        if "FLOOD_WAIT" in err.upper():
            return web.json_response({"error": "Telegram rate limit"}, status=429)
        return web.json_response({"error": str(e)}, status=500)

    return web.json_response({
        "results": results,
        "has_more": scanned >= 500 or len(results) >= DON_HANG_BATCH,
        "next_offset": last_id,
        "scanned": scanned,
        "mode": "live",
    })


async def donhang_page_handler(request: web.Request):
    return web.FileResponse("static/donhang.html")


async def donhang_msg_handler(request: web.Request):
    """Debug: fetch a single message by id from DON_HANG_CHAT_ID.
    GET /api/donhang/msg?id=N
    """
    if _client is None:
        return web.json_response({"error": "Telegram client not connected yet"}, status=503)
    try:
        mid = int(request.query.get("id", "0"))
    except ValueError:
        return web.json_response({"error": "bad id"}, status=400)
    msg = await _client.get_messages(DON_HANG_CHAT_ID, ids=mid)
    if msg is None:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response({
        "id": msg.id,
        "date": msg.date.isoformat() if msg.date else None,
        "text": msg.text or "",
        "raw_text": msg.raw_text or "",
        "message": msg.message or "",
        "has_hashtag_donhang_in_text": "#don_hang" in (msg.text or ""),
        "has_hashtag_donhang_in_raw": "#don_hang" in (msg.raw_text or ""),
        "media": type(msg.media).__name__ if msg.media else None,
    })


# ─── Main ──────────────────────────────────────────────────────────────────────
async def main():
    global _client, _donhang_db

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

    # ── "what data" fast order lookup in topics ─────────────────────────
    register_what_data_handler(client)

    # ── "gtr" fast command via Telethon (same speed as what_data) ────────
    from gtr_handler import register_gtr_handler
    register_gtr_handler(client)

    # ── #don_hang DB cache ────────────────────────────────────────────────
    _donhang_db = DonHangDB(DON_HANG_DB_PATH)
    print(f"💾 #don_hang DB: {DON_HANG_DB_PATH} — {_donhang_db.stats()}")
    register_live_handlers(client, _donhang_db, DON_HANG_CHAT_ID, DON_HANG_QUERY)

    async def _bootstrap_donhang():
        try:
            # Fill any gap since the server was last running.
            gained = await fill_gap_to_newest(client, _donhang_db, DON_HANG_CHAT_ID, DON_HANG_QUERY)
            if gained:
                print(f"📥 #don_hang gap-fill: +{gained} new messages")
            # Resume backfill (no-op once done).
            def _progress(scanned, matched, oldest_id):
                print(f"⏳ #don_hang backfill: scanned={scanned} matched={matched} oldest={oldest_id}", flush=True)
            res = await backfill(client, _donhang_db, DON_HANG_CHAT_ID, DON_HANG_QUERY, on_progress=_progress)
            print(f"✅ #don_hang backfill: {res}")
        except Exception as e:
            print(f"⚠️  #don_hang backfill error: {e}")

    asyncio.create_task(_bootstrap_donhang())

    # Start aiohttp
    app = web.Application()
    app.router.add_get("/", index_handler)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/api/search", search_handler)
    app.router.add_get("/api/donhang", donhang_handler)
    app.router.add_get("/api/donhang/stats", donhang_stats_handler)
    app.router.add_get("/api/donhang/msg", donhang_msg_handler)
    app.router.add_get("/donhang", donhang_page_handler)
    app.router.add_static("/static/", "static")

    # Edit a message via the user account (called from final_telegram instead of bot edit)
    from tg_edit import make_handler as _make_edit_handler
    app.router.add_post("/api/tg/edit-message", _make_edit_handler(lambda: _client))

    # Send a message via the user account (called from final_telegram instead of bot send)
    from tg_send import make_handler as _make_send_handler
    app.router.add_post("/api/tg/send-message", _make_send_handler(lambda: _client))

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
