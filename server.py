"""
server.py — Real-time Saved Messages monitor with WebSocket push.
Starts a Telethon listener on "Saved Messages" + aiohttp web server.
Clients connect via WebSocket at ws://localhost:8080/ws
"""
import asyncio
import json
import logging
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
from utils.logger import configure_logging

load_dotenv()
configure_logging()
log = logging.getLogger("server")

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
PHONE = os.getenv("PHONE", "")
PORT = int(os.getenv("PORT", 8080))

if not all([API_ID, API_HASH, PHONE]):
    log.error("Missing .env config!")
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
    log.info("Loaded %d recent messages", len(recent_messages))


async def broadcast(data: dict, persist=True):
    """Send JSON to all connected WebSocket clients."""
    if persist:
        recent_messages.append(data)
        # Keep only last 500
        if len(recent_messages) > 500:
            recent_messages.pop(0)

    payload = json.dumps(data, default=str)
    log.debug("Broadcasting type=%s to %d clients", data.get("type", "?"), len(ws_clients))
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
        log.debug("Using pi CLI backend for chat %s", chat_id)
        return await ask_pi(chat_id, question)
    else:
        log.debug("Using Fireworks API backend for chat %s", chat_id)
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
            log.info("Auto-replied 'yes' to %s", label)


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
        log.info("New: %s: %s", sender['name'], (msg.text or '[media]')[:80])
        log.debug("New msg id=%d media=%s reply_to=%s", msg.id, type(msg.media).__name__ if msg.media else None, msg.reply_to_msg_id)
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
            log.info("Group - %s: %s", sender['name'], text[:80])

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
            log.info("Replied with AI answer (%d chars)", len(answer))

    @client.on(events.MessageEdited(chats="me"))
    async def on_message_edited(event):
        msg = event.message
        data = {
            "type": "edit",
            "id": msg.id,
            "date": msg.date.isoformat(),
            "text": msg.text[:1000] if msg.text else None,
        }
        log.info("Edited msg %d", msg.id)
        log.debug("Edit text len=%d", len(msg.text) if msg.text else 0)
        await broadcast(data)

    @client.on(events.MessageDeleted(chats="me"))
    async def on_message_deleted(event):
        data = {
            "type": "delete",
            "ids": event.deleted_ids or [],
        }
        log.info("Deleted: %s", data['ids'])
        await broadcast(data)

    # ── Inline keyboard callback handler ──────────────────────────────────────
    @client.on(events.CallbackQuery)
    async def on_callback(event):
        data = event.data.decode()
        sender = await event.get_sender()
        sname = sender_info(sender)["name"]
        await event.answer(f"You clicked: {data}", alert=False)
        log.info("%s clicked: %s", sname, data)
        await event.edit(f"yes — {sname} chose **{data.upper()}**")


# ─── HTTP / WebSocket routes ──────────────────────────────────────────────────
async def index_handler(request: web.Request):
    return web.FileResponse("static/index.html")


async def websocket_handler(request: web.Request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    ws_clients.add(ws)
    log.info("Client connected (%d total)", len(ws_clients))

    # Send recent message history
    history = {"type": "history", "messages": recent_messages}
    log.debug("Sending history (%d msgs) to new client", len(recent_messages))
    await ws.send_str(json.dumps(history, default=str))

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                if msg.data == "history":
                    log.debug("Client requested history resend")
                    history = {"type": "history", "messages": recent_messages}
                    await ws.send_str(json.dumps(history, default=str))
            elif msg.type == web.WSMsgType.ERROR:
                log.warning("WS error: %s", ws.exception())
    finally:
        ws_clients.discard(ws)
        log.info("Client disconnected (%d total)", len(ws_clients))
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
            log.error("Server search error: %s", e)
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
            log.error("Deep scan fetch error: %s", e)
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

    log.debug("search q=%r offset=%d mode=%s", q, offset_id, mode)

    # Cache check
    cache_key = f"{q}:{offset_id}:{mode}"
    now = time.monotonic()
    cached = RESULT_CACHE.get(cache_key)
    if cached and (now - cached["ts"]) < RESULT_CACHE_TTL_SEC:
        log.debug("search cache hit for %r", cache_key)
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
        log.info("Server returned 0 results for '%s', starting deep scan...", q)
        try:
            results, has_more, next_offset, total_searched = await _deep_search(q, offset_id)
            used_mode = "deep"
        except Exception as e:
            err = str(e)
            if "FLOOD_WAIT" in err.upper():
                return web.json_response({
                    "error": "Telegram rate limit — deep scan paused. Try again in a moment.",
                }, status=429)
            log.error("Deep search error: %s", e)

    log.debug("search result: mode=%s results=%d has_more=%s", used_mode, len(results), has_more)

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

    log.debug("donhang offset=%d q=%r mode=%s", offset_id, q, mode)

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


# ─── Orders viewer (shared app.db) ────────────────────────────────────────────
import sqlite3 as _sqlite3

_ORDERS_DB_PATH = os.path.expanduser(
    os.getenv("SHARED_DB_PATH", "~/Documents/final_telegram/data/app.db")
)

def _get_orders_conn():
    """Read-only connection to the shared orders DB."""
    conn = _sqlite3.connect(_ORDERS_DB_PATH, check_same_thread=False)
    conn.row_factory = _sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


async def orders_api_handler(request: web.Request):
    """GET /api/orders?page=1&limit=50&search=&status=
    Returns paginated orders from shared app.db."""
    try:
        page = max(1, int(request.query.get("page", "1")))
    except ValueError:
        page = 1
    try:
        limit = max(1, min(200, int(request.query.get("limit", "50"))))
    except ValueError:
        limit = 50
    search = request.query.get("search", "").strip()
    status = request.query.get("status", "").strip()

    offset = (page - 1) * limit

    where = ["o.deleted_at IS NULL"]
    params = []

    if search:
        where.append("(o.json LIKE ? OR o.firebase_key LIKE ?)")
        p = f"%{search}%"
        params.extend([p, p])

    if status:
        where.append("json_extract(o.json, '$.trang_thai') = ?")
        params.append(status)

    where_clause = " AND ".join(where)

    sort = request.query.get("sort", "updated").strip()

    conn = _get_orders_conn()
    try:
        # Count total
        count_row = conn.execute(
            f"SELECT COUNT(*) FROM orders o WHERE {where_clause}", params
        ).fetchone()
        total = count_row[0] if count_row else 0

        # Sort selection
        # has_data: records with customer name are "real" orders (both old & new structure)
        has_data = (
            "(json_extract(o.json, '$.hoadon.print_content.kh') IS NOT NULL "
            " AND json_extract(o.json, '$.hoadon.print_content.kh') != '') "
            "OR (json_extract(o.json, '$.customer_name') IS NOT NULL "
            " AND json_extract(o.json, '$.customer_name') != '')"
        )
        if sort == "date":
            # Sort by invoice datetime (DD/MM/YYYY HH:MM → YYYY-MM-DD HH:MM)
            dt_raw = "json_extract(o.json, '$.hoadon.print_content.datetime')"
            dt_expr = (
                f"substr({dt_raw}, 7, 4) || '-' || "
                f"substr({dt_raw}, 4, 2) || '-' || "
                f"substr({dt_raw}, 1, 2) || ' ' || "
                f"substr({dt_raw}, 12, 5)"
            )
            has_dt = f"{dt_raw} IS NOT NULL AND {dt_raw} != ''"
            order_by = (
                f"CASE WHEN {has_data} THEN 0 ELSE 1 END ASC, "
                f"CASE WHEN {has_dt} THEN 0 ELSE 1 END ASC, "
                f"CASE WHEN {has_dt} THEN {dt_expr} ELSE json_extract(o.json, '$.created') END DESC"
            )
        elif sort == "created":
            # Sort by JSON created timestamp (ISO 8601 string, naturally sortable)
            order_by = (
                f"CASE WHEN {has_data} THEN 0 ELSE 1 END ASC, "
                f"json_extract(o.json, '$.created') DESC, o.thread_id DESC"
            )
        else:
            # Default: real orders first, then by updated_at DESC
            order_by = (
                f"CASE WHEN {has_data} THEN 0 ELSE 1 END ASC, "
                f"o.updated_at DESC, o.thread_id DESC"
            )

        rows = conn.execute(
            f"""SELECT o.firebase_key, o.thread_id, o.channel_id, o.message_id,
                       o.json, o.updated_at
                FROM orders o
                WHERE {where_clause}
                ORDER BY {order_by}
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()

        orders = []
        for r in rows:
            try:
                j = json.loads(r["json"])
            except Exception:
                j = {}
            hd = j.get("hoadon", {}) or {}
            pc = hd.get("print_content", {}) or {}

            # Support both old and new data structures
            # Old: hoadon.print_content.kh, tongthanhtoan, datetime, sdt, hd_code
            # New: customer_name, invoice[], created, text, kiotvietInvoiceCode
            customer = pc.get("kh") or j.get("customer_name", "")
            hd_code = hd.get("hd_code") or j.get("kiotvietInvoiceCode", "")
            phone = pc.get("sdt", "")
            date = pc.get("datetime", "")
            order_total = pc.get("tongthanhtoan", "")
            no_truoc = pc.get("no_truoc", "")
            tongtienhang = pc.get("tongtienhang", "")
            invoice_count = len(pc.get("invoice", []) or [])

            # If new structure (no hoadon.print_content), calculate from top-level fields
            if not customer and j.get("customer_name"):
                customer = j.get("customer_name")
            if not hd_code and j.get("kiotvietInvoiceCode"):
                hd_code = j.get("kiotvietInvoiceCode")
            if not date and j.get("created"):
                # Format ISO to DD/MM/YYYY HH:MM
                created = j.get("created", "")
                if len(created) >= 16:
                    date = created[8:10] + "/" + created[5:7] + "/" + created[:4] + " " + created[11:16]
            if not order_total and j.get("invoice"):
                t = 0
                for item in j.get("invoice", []):
                    p = item.get("price", 0) or 0
                    sl = item.get("sl", item.get("quantity", 0)) or 0
                    t += p * sl
                if t > 0:
                    order_total = f"{t:,}".replace(",", ".")
            if not invoice_count and j.get("invoice"):
                invoice_count = len(j.get("invoice", []))

            creator = j.get("nguoi_tao_HD")
            if isinstance(creator, list):
                creator = ", ".join(str(x) for x in creator)
            else:
                creator = str(creator) if creator else ""

            orders.append({
                "key": r["firebase_key"],
                "thread_id": r["thread_id"],
                "channel_id": r["channel_id"],
                "message_id": r["message_id"],
                "customer": customer,
                "total": order_total,
                "phone": phone,
                "date": date,
                "status": j.get("trang_thai", ""),
                "soan": j.get("soan", False),
                "giao": j.get("giao", False),
                "nop": j.get("nop", False),
                "nhan": j.get("nhan", False),
                "done_after_20250124": j.get("done_after_20250124", False),
                "updated_at": r["updated_at"],
                "hd_code": hd_code,
                "creator": creator,
                "topic_name": j.get("topic_name", ""),
                "invoice_count": invoice_count,
                "no_truoc": no_truoc,
                "tongtienhang": tongtienhang,
            })

        total = int(total) if total else 0
        total_pages = max(1, (total + limit - 1) // limit)

        return web.json_response({
            "orders": orders,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        })
    finally:
        conn.close()


async def orders_page_handler(request: web.Request):
    return web.FileResponse("static/orders.html")


async def order_detail_handler(request: web.Request):
    """GET /api/order/{thread_id}
    Return full order row JSON for the detail modal.
    """
    thread_id = request.match_info.get("thread_id", "").strip()
    if not thread_id:
        return web.json_response({"error": "missing thread_id"}, status=400)

    conn = _get_orders_conn()
    try:
        row = conn.execute(
            """SELECT firebase_key, thread_id, channel_id, message_id,
                      json, updated_at
               FROM orders
               WHERE thread_id = ? AND deleted_at IS NULL""",
            (thread_id,),
        ).fetchone()

        if row is None:
            return web.json_response({"error": "not found"}, status=404)

        try:
            j = json.loads(row["json"])
        except Exception:
            j = {}

        return web.json_response({
            "key": row["firebase_key"],
            "thread_id": row["thread_id"],
            "channel_id": row["channel_id"],
            "message_id": row["message_id"],
            "updated_at": row["updated_at"],
            "data": j,
        })
    finally:
        conn.close()


# ─── Payment handlers (REST API for bot-don-hang) ────────────────────────────

async def _payment_handler(request: web.Request, method: str):
    """POST /api/order/payment/{tm|ck}
    Process payment from bot-don-hang. Mirrors Telethon ck/tm commands.
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    thread_id = body.get("thread_id")
    amount = body.get("amount")
    user_id = body.get("user_id")

    if not thread_id or not amount:
        return web.json_response({"ok": False, "error": "Missing thread_id or amount"}, status=400)

    try:
        from order_commands_v3 import _process_payment_core
        result = await _process_payment_core(int(thread_id), int(amount), user_id, method)
    except Exception as e:
        log.error("Payment API error: %s", e, exc_info=True)
        return web.json_response({"ok": False, "error": str(e)}, status=500)

    if not result["success"]:
        return web.json_response({"ok": False, "error": result["error"]}, status=400)

    return web.json_response({
        "ok": True,
        "thread_id": result["thread_id"],
        "amount": result["amount"],
        "method": result["method"],
        "method_label": result["method_label"],
        "kv_code": result["kv_code"],
        "old_debt": result["old_debt"],
        "new_debt": result["new_debt"],
    })


async def payment_tm_handler(request: web.Request):
    return await _payment_handler(request, "Cash")


async def payment_ck_handler(request: web.Request):
    return await _payment_handler(request, "Transfer")


async def order_totals_handler(request: web.Request):
    """POST /api/order/totals
    Return order totals for amount suggestion (used by bot-don-hang payment flow).
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    thread_id = body.get("thread_id")
    if not thread_id:
        return web.json_response({"ok": False, "error": "Missing thread_id"}, status=400)

    try:
        from order_db import _get_connection, get_order_by_thread_id
        conn = _get_connection()
        order = get_order_by_thread_id(conn, int(thread_id))
        if not order:
            return web.json_response({"ok": False, "error": "Order not found"}, status=404)

        # Calculate totals from invoice if available
        invoice = order.get("invoice") or order.get("san_pham") or []
        total = sum(int(item.get("price", 0)) * int(item.get("sl", 1)) for item in invoice)
        discount = order.get("discount", 0)
        pvc = order.get("pvc", 0)
        vat = order.get("vat", 0)
        pre_debt_total = total - discount + pvc + vat

        return web.json_response({
            "ok": True,
            "order": {
                "pre_debt_total": pre_debt_total,
                "total_payable": pre_debt_total,
                "total": total,
                "discount": discount,
                "pvc": pvc,
                "vat": vat,
            }
        })
    except Exception as e:
        log.error("Totals API error: %s", e, exc_info=True)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def auto_parse_handler(request: web.Request):
    """POST /api/order/auto-parse
    Auto-detect invoice items from order text. Called by channelDonHangMoi.js
    when a new #don_hang order is created.
    Body: { thread_id: int, text: str }
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    thread_id = body.get("thread_id")
    text = body.get("text", "").strip()
    if not thread_id or not text:
        return web.json_response({"ok": False, "error": "Missing thread_id or text"}, status=400)

    from order_db import _get_connection, get_order_by_thread_id, parse_invoice_free_text, _save_order
    conn = _get_connection()

    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return web.json_response({"ok": False, "error": "Order not found in SQLite"}, status=404)

    kh_id_fb = order.get("khach_hang_id") or order.get("khID")
    invoice = parse_invoice_free_text(conn, text, kh_id_fb)
    if not invoice:
        return web.json_response({"ok": True, "parsed": 0, "message": "No invoice items detected"})

    from product_db import freeze_invoice_cost_prices
    order["invoice"] = freeze_invoice_cost_prices(conn, invoice)
    ok = _save_order(conn, thread_id, order)
    if not ok:
        return web.json_response({"ok": False, "error": "Failed to save order"}, status=500)

    log.info("auto-parse: thread=%d items=%d", thread_id, len(invoice))

    # Build notification lines
    lines = []
    if _client is not None:
        # ── Invoice section ──
        if invoice:
            lines.append(f"🤖 <b>Auto-detect:</b> đã tìm thấy {len(invoice)} sản phẩm\n")
            grand_total = 0
            for item in invoice:
                sp = item.get("sp", "?")
                sl = item.get("sl", 0)
                price = item.get("price", 0)
                sub_total = sl * price
                grand_total += sub_total
                lines.append(f"• <b>{sp}</b> x{sl} @ {price:,}đ = <b>{sub_total:,}đ</b>")
            lines.append(f"\n💰 <b>Tổng cộng: {grand_total:,}đ</b>")

        # ── Customer detection section ──
        from order_db import detect_customer_free_text, get_customer_by_key
        detection = detect_customer_free_text(conn, text)
        if detection["autoAssign"]:
            cust = detection["autoAssign"]
            # Auto-assign
            order["khach_hang_id"] = cust["customerID"]
            order["customer_name"] = cust["customerName"]
            _save_order(conn, thread_id, order)
            if lines:
                lines.append("")
            lines.append(f"👤 <b>Đã gán:</b> {cust['customerName']} ({cust['score']}%)")
            lines.append(f"🎯 Mẫu: \"{cust['bestMatchedPattern']}\"")
        elif detection["matches"]:
            matches = detection["matches"][:3]
            if lines:
                lines.append("")
            lines.append(f"🔍 <b>Khách hàng có thể:</b>")
            for i, m in enumerate(matches):
                lines.append(f"  {i+1}. {m['customerName']} ({m['score']}%) — <code>add khach hang {m['customerID']}</code>")

        # Send
        if lines:
            try:
                order_group_id = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
                await _client.send_message(
                    order_group_id,
                    "\n".join(lines),
                    reply_to=thread_id,
                    parse_mode="html",
                )
            except Exception as e:
                log.warning("auto-parse notification failed: %s", e)

    return web.json_response({
        "ok": True,
        "parsed": len(invoice),
        "auto_assigned": detection["autoAssign"]["customerID"] if detection.get("autoAssign") else None,
    })


# ── Task/invoice endpoints for bot-don-hang (replaces Node.js HTTP calls) ──────

def _make_task_handler(task_type: str):
    """Factory: creates handler for POST /api/order/{soan|ban|giao|nop-tien}."""
    async def handler(request: web.Request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
        body["type"] = task_type
        return await api_task_handler_impl(body)
    return handler


async def api_task_handler(request: web.Request):
    """POST /api/order/task  { thread_id, type, user_id? }"""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    return await api_task_handler_impl(body)


async def api_task_handler_impl(body: dict):
    thread_id = body.get("thread_id")
    task_type = body.get("type")
    user_id = body.get("user_id")
    if not thread_id or not task_type:
        return web.json_response({"ok": False, "error": "Missing thread_id or type"}, status=400)

    from order_db import _get_connection, get_order_by_thread_id, set_task_status, _save_order
    conn = _get_connection()
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return web.json_response({"ok": False, "error": "Order not found"}, status=404)

    TASK_MAP = {"soan": "soan_hang", "ban": "ban_hd", "giao": "giao_hang", "nop": "nop_tien"}
    TASK_NAMES = {"soan_hang": "soạn hàng", "ban_hd": "bán HĐ", "giao_hang": "giao hàng", "nop_tien": "nộp tiền"}
    internal_type = TASK_MAP.get(task_type, task_type)
    set_task_status(conn, thread_id, internal_type, user_id)
    # Re-read after update
    order = get_order_by_thread_id(conn, thread_id)

    # Background: send notification + refresh main message
    task_name = TASK_NAMES.get(internal_type, internal_type)
    actor = "Hệ thống"
    if user_id:
        try:
            entity = await _client.get_entity(user_id)
            actor = entity.first_name or str(user_id)
        except Exception:
            actor = str(user_id)

    order_group_id = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
    client.loop.create_task(_send_task_notification(order_group_id, thread_id, f"{actor} {task_name}"))
    # Refresh main message
    channel_id = order.get("channel_id")
    message_id = order.get("message_id")
    if channel_id and message_id:
        client.loop.create_task(_refresh_order_bg(conn, thread_id, channel_id, message_id))
    return web.json_response({"ok": True, "task": internal_type})


async def _send_task_notification(chat_id, thread_id, message):
    """Send task notification to order thread via Telethon user client."""
    try:
        await _client.send_message(chat_id, message, reply_to=thread_id, disable_web_page_preview=True)
    except Exception as e:
        log.warning("Task notification failed: %s", e)


async def _refresh_order_bg(conn, thread_id, channel_id, message_id):
    """Refresh main message in background (uses Node.js renderer for now)."""
    try:
        from order_db import _call_final_telegram, get_order_by_thread_id
        order = get_order_by_thread_id(conn, thread_id)
        if not order:
            return
        _call_final_telegram("/api/update-order-message", {
            "order": order, "message_id": message_id, "channel_id": channel_id,
        }, timeout=10)
    except Exception:
        pass


# ── Additional bot-don-hang endpoints ────────────────────────────────

async def api_fix_handler(request: web.Request):
    """POST /api/order/fix  { thread_id, text, user_id? }
    Update order text in SQLite directly.
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    thread_id = body.get("thread_id")
    text = (body.get("text") or "").strip()
    if not thread_id or not text:
        return web.json_response({"ok": False, "error": "Missing thread_id or text"}, status=400)

    from order_db import _get_connection, get_order_by_thread_id, _save_order
    conn = _get_connection()
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return web.json_response({"ok": False, "error": "Order not found"}, status=404)

    order["text"] = text
    order["text_raw"] = text
    if not _save_order(conn, thread_id, order):
        return web.json_response({"ok": False, "error": "Failed to save"}, status=500)

    # Refresh main message in background
    channel_id = order.get("channel_id")
    message_id = order.get("message_id")
    if channel_id and message_id:
        client.loop.create_task(_refresh_order_bg(conn, thread_id, channel_id, message_id))
    return web.json_response({"ok": True})


async def api_invoice_update_handler(request: web.Request):
    """POST /api/order/invoice/update  { thread_id, invoice: [...] }
    Update invoice items in SQLite directly.
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    thread_id = body.get("thread_id")
    invoice = body.get("invoice")
    if not thread_id or not isinstance(invoice, list):
        return web.json_response({"ok": False, "error": "Missing thread_id or invoice"}, status=400)

    from order_db import _get_connection, get_order_by_thread_id, _save_order
    from product_db import freeze_invoice_cost_prices
    conn = _get_connection()
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return web.json_response({"ok": False, "error": "Order not found"}, status=404)

    order["invoice"] = freeze_invoice_cost_prices(conn, invoice)
    if not _save_order(conn, thread_id, order):
        return web.json_response({"ok": False, "error": "Failed to save"}, status=500)

    # Refresh main message
    channel_id = order.get("channel_id")
    message_id = order.get("message_id")
    if channel_id and message_id:
        client.loop.create_task(_refresh_order_bg(conn, thread_id, channel_id, message_id))
    log.info("invoice-update: thread=%d items=%d", thread_id, len(invoice))
    return web.json_response({"ok": True})


async def api_reply_handler(request: web.Request):
    """POST /api/order/reply  { thread_id, text, times? }
    Send reply message to order thread via Telethon.
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    thread_id = body.get("thread_id")
    text = (body.get("text") or "").strip()
    times = body.get("times", 1)
    if not thread_id or not text:
        return web.json_response({"ok": False, "error": "Missing thread_id or text"}, status=400)

    order_group_id = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
    try:
        for _ in range(min(times, 5)):
            await _client.send_message(order_group_id, text, reply_to=thread_id)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)
    return web.json_response({"ok": True})


async def api_customer_price_handler(request: web.Request):
    """POST /api/customer/price  { customer_id, product }
    Get customer-specific price for a product from SQLite.
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    customer_id = body.get("customer_id")
    product = (body.get("product") or "").upper().strip()
    if not customer_id or not product:
        return web.json_response({"ok": False, "error": "Missing customer_id or product"}, status=400)

    from order_db import _get_connection, get_customer_price_list
    conn = _get_connection()
    price_list = get_customer_price_list(conn, str(customer_id))
    price = price_list.get(product, 0)
    return web.json_response({"ok": True, "price": price, "product": product})


async def api_refresh_handler(request: web.Request):
    """POST /api/order/refresh  { thread_id }
    Refresh main message via Node.js renderer (keep for channel message editing).
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    thread_id = body.get("thread_id")
    if not thread_id:
        return web.json_response({"ok": False, "error": "Missing thread_id"}, status=400)

    from order_db import _get_connection, get_order_by_thread_id
    conn = _get_connection()
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return web.json_response({"ok": False, "error": "Order not found"}, status=404)

    from order_db import _call_final_telegram
    channel_id = order.get("channel_id")
    message_id = order.get("message_id")
    if channel_id and message_id:
        try:
            _call_final_telegram("/api/update-order-message", {
                "order": order, "message_id": message_id, "channel_id": channel_id,
            }, timeout=10)
        except Exception:
            pass
    return web.json_response({"ok": True})


# ─── Main ──────────────────────────────────────────────────────────────────────
async def main():
    global _client, _donhang_db

    # Start Telethon
    client = TelegramClient("user_session", API_ID, API_HASH)
    _client = client
    await client.start(phone=PHONE)
    me = await client.get_me()
    log.info("Logged in as %s", me.first_name)
    log.info("Listening to Saved Messages...")

    # Load recent message history
    await load_recent_messages(client, limit=100)
    register_handlers(client)

    # ── "what data" fast order lookup in topics ─────────────────────────
    register_what_data_handler(client)

    # ── "gtr" fast command via Telethon (same speed as what_data) ────────
    from gtr_handler import register_gtr_handler
    register_gtr_handler(client)
    from order_commands import register_order_commands
    register_order_commands(client)
    from order_commands_v2 import register_order_commands_v2
    register_order_commands_v2(client)
    from order_commands_v3 import register_order_commands_v3
    register_order_commands_v3(client)

    # ── "gdt / ingdt" giấy dán thùng commands ─────────────────────────────
    from gdt_handler import register_gdt_handler
    register_gdt_handler(client)

    # ── "newkh" create customer + topic in KhachHang group ───────────────
    from newkh_handler import register_newkh_handler
    register_newkh_handler(client)

    # ── product price lookup / personal price in KhachHang group ─────────
    from khachhang_commands import register_khachhang_commands
    register_khachhang_commands(client)

    # ── product management + profit commands ────────────────────────────
    from product_commands import register_product_commands
    register_product_commands(client)

    # ── profit dashboard web server ─────────────────────────────────────
    from profit_dashboard import create_app as create_profit_app, DASHBOARD_PORT
    profit_app = create_profit_app()
    profit_runner = web.AppRunner(profit_app)
    await profit_runner.setup()
    profit_site = web.TCPSite(profit_runner, "0.0.0.0", DASHBOARD_PORT)
    await profit_site.start()
    log.info("Profit dashboard: http://localhost:%d", DASHBOARD_PORT)

    # ── Firebase html-to-png listener (replaces test-qwen2-main Node service) ─
    from firebase_html_to_png import start_listener as _start_html_to_png
    _start_html_to_png(client)

    # ── #don_hang DB cache ────────────────────────────────────────────────
    _donhang_db = DonHangDB(DON_HANG_DB_PATH)
    log.info("#don_hang DB: %s — %s", DON_HANG_DB_PATH, _donhang_db.stats())
    register_live_handlers(client, _donhang_db, DON_HANG_CHAT_ID, DON_HANG_QUERY)

    async def _bootstrap_donhang():
        try:
            log.debug("Starting donhang bootstrap: gap-fill + backfill")
            # Fill any gap since the server was last running.
            gained = await fill_gap_to_newest(client, _donhang_db, DON_HANG_CHAT_ID, DON_HANG_QUERY)
            if gained:
                log.info("#don_hang gap-fill: +%d new messages", gained)
            # Resume backfill (no-op once done).
            def _progress(scanned, matched, oldest_id):
                log.info("#don_hang backfill: scanned=%d matched=%d oldest=%d", scanned, matched, oldest_id)
            res = await backfill(client, _donhang_db, DON_HANG_CHAT_ID, DON_HANG_QUERY, on_progress=_progress)
            log.info("#don_hang backfill: %s", res)
        except Exception as e:
            log.warning("#don_hang backfill error: %s", e)

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
    app.router.add_get("/orders", orders_page_handler)
    app.router.add_get("/api/orders", orders_api_handler)
    app.router.add_get("/api/order/{thread_id}", order_detail_handler)
    app.router.add_static("/static/", "static")

    # Edit a message via the user account (called from final_telegram instead of bot edit)
    from tg_edit import make_handler as _make_edit_handler
    app.router.add_post("/api/tg/edit-message", _make_edit_handler(lambda: _client))

    # Send a message via the user account (called from final_telegram instead of bot send)
    from tg_send import make_handler as _make_send_handler
    app.router.add_post("/api/tg/send-message", _make_send_handler(lambda: _client))

    # Send a file via the user account (called from bot-don-hang for media forwarding)
    from tg_send_file import make_handler as _make_send_file_handler
    app.router.add_post("/api/tg/send-file", _make_send_file_handler(lambda: _client))

    # Payment endpoints (called from bot-don-hang, mirrors ck/tm Telethon commands)
    app.router.add_post("/api/order/payment/tm", payment_tm_handler)
    app.router.add_post("/api/order/payment/ck", payment_ck_handler)
    app.router.add_post("/api/order/totals", order_totals_handler)

    # Auto-parse invoice items from order text (called by channelDonHangMoi.js on new order)
    app.router.add_post("/api/order/auto-parse", auto_parse_handler)
    # Task endpoints (replaces Node.js /api/order/soan, /ban, /giao, /nop-tien)
    app.router.add_post("/api/order/soan", _make_task_handler("soan"))
    app.router.add_post("/api/order/ban", _make_task_handler("ban"))
    app.router.add_post("/api/order/giao", _make_task_handler("giao"))
    app.router.add_post("/api/order/nop-tien", _make_task_handler("nop"))
    app.router.add_post("/api/order/refresh-view", api_refresh_handler)
    app.router.add_post("/api/order/fix", api_fix_handler)
    app.router.add_post("/api/order/invoice/update", api_invoice_update_handler)
    app.router.add_post("/api/order/reply", api_reply_handler)
    app.router.add_post("/api/customer/price", api_customer_price_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info("Web server: http://localhost:%d", PORT)
    log.info("─" * 50)

    # Run both forever
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutting down.")
