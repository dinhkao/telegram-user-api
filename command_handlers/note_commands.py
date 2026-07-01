"""Note (ghi chú) group bot — ported from node bots/groupNote.js.

Manages "note" forum topics keyed by thread_id (text, tags[], check, del,
channel_id, message_id). SQLite-native (note_store) instead of node's
Firebase `le_trang_note/{thread}`.

IMPORTANT — scope: this file only *edits* existing notes, exactly like the
node source (`if (!note) return` whenever a note isn't found for the current
topic). Note *creation* is not part of groupNote.js and no telethon source
for it was found in this codebase, so it is intentionally out of scope here.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3

from telethon import events
from telethon.tl.types import MessageService
from telethon.tl.functions.messages import EditForumTopicRequest

from note_store import (
    create_note_table,
    migrate_note_table,
    get_note,
    set_text,
    set_tags,
    set_check,
    set_del,
)

from .thread_utils import extract_thread_id

log = logging.getLogger("note")
GROUP_NOTE_ID = int(os.getenv("GROUP_NOTE_ID", "-1003053046732"))
SHARED_DB_PATH = os.path.expanduser(os.getenv("SHARED_DB_PATH", "~/letrang-db/app.db"))


def _conn():
    conn = sqlite3.connect(SHARED_DB_PATH, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


# ─── tag normalization (node normalizeTag) ──────────────────────────────────
def normalize_tag(raw) -> str | None:
    if not raw:
        return None
    t = str(raw).strip()
    if not t:
        return None
    if t.startswith("#"):
        t = t[1:]
    t = t.lower()
    t = re.sub(r"\s+", "_", t)
    t = re.sub(r"[^\w]", "", t, flags=re.UNICODE)  # keep \p{L}\p{Nd}_ equivalent
    if not t:
        return None
    return "#" + t


def _escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ─── channel message render (node formatChannelMessage) ────────────────────
def format_channel_message(note: dict) -> str:
    positive_id = str(GROUP_NOTE_ID).replace("-100", "")
    base_link = (
        f'<a href="tg://privatepost?channel={positive_id}&post={note.get("thread_id")}">'
        f'{note.get("text") or ""}</a>'
    )
    base = f"<s>{base_link}</s>" if note.get("del") else base_link
    tags = note.get("tags") or []
    tags_line = f"<b>Tags:</b> {' '.join(tags)}" if tags else ""
    check_line = f"<b>Check:</b> {'✅' if note.get('check') else '❌'}"
    details = "\n".join(x for x in (tags_line, check_line) if x)
    status_tag = "#lt_note_đã_xong" if note.get("check") else "#lt_note_chưa_xong"
    body = f"\n<blockquote expandable>{details}</blockquote>" if details else ""
    return f"{base}{body}\n{status_tag}"


HELP_TEXT = (
    "*Ghi chú (+note)*\n"
    "- `fix <nội dung>`: Sửa nội dung ghi chú\n"
    "- `fixsi <nội dung>`: Sửa nội dung (silent)\n"
    "- `fixapp <nội dung>`: Nối thêm nội dung\n"
    "- `add tag <tag...>`: Thêm tag vào ghi chú\n"
    "- `remove tag <tag...>`: Xóa tag\n"
    "- `check`: Bật/tắt trạng thái check\n"
    "- `del`: Đánh dấu xóa (gạch ngang nội dung kênh)\n"
    "- `update`: Cập nhật lại hiển thị note ở kênh\n"
    "- `getjson`: Xem dữ liệu ghi chú"
)


def register_note_commands(client):
    conn = _conn()
    create_note_table(conn)
    migrate_note_table(conn)
    log.info("note handler listening on group %d. DB: %s", GROUP_NOTE_ID, SHARED_DB_PATH)

    async def reply(msg, text, parse_mode=None):
        await client.send_message(msg.chat_id, text, reply_to=msg.id, parse_mode=parse_mode)

    async def rename_topic(thread_id, name):
        try:
            await client(EditForumTopicRequest(peer=GROUP_NOTE_ID, topic_id=thread_id, title=name))
        except Exception:  # noqa: BLE001 — best-effort, matches node's empty catch {}
            pass

    async def edit_channel_message(note):
        """Best-effort channel edit — errors are logged, never surfaced (matches
        node's `catch (e) { console.error(...) }` used everywhere except `update`)."""
        channel_id, message_id = note.get("channel_id"), note.get("message_id")
        if not channel_id or not message_id:
            return
        try:
            text = format_channel_message(note)
            await client.edit_message(int(channel_id), int(message_id), text, parse_mode="html")
        except Exception as e:  # noqa: BLE001
            log.error("Failed to edit main note message in channel: %s", e)

    @client.on(events.NewMessage(chats=GROUP_NOTE_ID))
    async def on_group_msg(event):
        msg = event.message
        if isinstance(msg, MessageService) or not msg.text:
            return
        t = msg.text.strip()
        low = t.lower()

        # help — mirrors node: no thread/note lookup at all
        if low == "?":
            await reply(msg, HELP_TEXT, parse_mode="md")
            return

        thread_id = extract_thread_id(msg)
        note = get_note(conn, thread_id) if thread_id else None
        if not note:
            return  # note not found for this topic → silent, like node `if (!note) return`

        # fixsi <text> (silent ack) — must be checked before the plain "fix " prefix
        if re.match(r"^fixsi\b", t, re.IGNORECASE):
            new_text = re.sub(r"^fixsi\b", "", t, count=1, flags=re.IGNORECASE).strip()
            if not new_text:
                return
            set_text(conn, thread_id, new_text)
            await rename_topic(thread_id, new_text)
            note["text"] = new_text
            await edit_channel_message(note)
            await reply(msg, "✅ Đã cập nhật nội dung ghi chú (silent).")
            return

        # fixapp <text> (append to existing) — also before plain "fix "
        if re.match(r"^fixapp\b", t, re.IGNORECASE):
            append_part = re.sub(r"^fixapp\b", "", t, count=1, flags=re.IGNORECASE).strip()
            old_text = (note.get("text") or "").strip()
            combined = f"{old_text} {append_part}".strip() if old_text else append_part
            set_text(conn, thread_id, combined)
            await rename_topic(thread_id, combined)
            note["text"] = combined
            await edit_channel_message(note)
            await reply(msg, "✅ Đã nối thêm nội dung ghi chú.")
            return

        # fix <text>
        if re.match(r"^fix\s+", t, re.IGNORECASE):
            new_text = re.sub(r"^fix\s+", "", t, count=1, flags=re.IGNORECASE).strip()
            if not new_text:
                return
            set_text(conn, thread_id, new_text)
            await rename_topic(thread_id, new_text)
            note["text"] = new_text
            await edit_channel_message(note)
            await reply(msg, "✅ Đã cập nhật nội dung ghi chú.")
            return

        # add tag <tag...>
        if re.match(r"^add\s+tag\b", t, re.IGNORECASE):
            raw = re.sub(r"^add\s+tag\b", "", t, count=1, flags=re.IGNORECASE).strip()
            if not raw:
                await reply(msg, "❌ Vui lòng nhập tag. Ví dụ: add tag urgent")
                return
            parts = [p for p in re.split(r"[\s,]+", raw) if p]
            to_add = [tag for tag in (normalize_tag(p) for p in parts) if tag]
            tags = list(note.get("tags") or [])
            added = []
            for tag in to_add:
                if tag not in tags:
                    tags.append(tag)
                    added.append(tag)
            set_tags(conn, thread_id, tags)
            note["tags"] = tags
            await edit_channel_message(note)
            if added:
                display = " ".join(tag.lstrip("#") for tag in added)
                await reply(msg, f"✅ Đã thêm tag: {display}")
            else:
                await reply(msg, "ℹ️ Tag đã tồn tại, không có gì thay đổi.")
            return

        # remove tag <tag...>
        if re.match(r"^remove\s+tag\b", t, re.IGNORECASE):
            raw = re.sub(r"^remove\s+tag\b", "", t, count=1, flags=re.IGNORECASE).strip()
            if not raw:
                await reply(msg, "❌ Vui lòng nhập tag cần xóa. Ví dụ: remove tag urgent")
                return
            parts = [p for p in re.split(r"[\s,]+", raw) if p]
            to_remove = {tag for tag in (normalize_tag(p) for p in parts) if tag}
            before = list(note.get("tags") or [])
            tags = [tag for tag in before if tag not in to_remove]
            set_tags(conn, thread_id, tags)
            note["tags"] = tags
            await edit_channel_message(note)
            removed = [tag for tag in before if tag not in tags]
            if removed:
                display = " ".join(tag.lstrip("#") for tag in removed)
                await reply(msg, f"🗑️ Đã xóa tag: {display}")
            else:
                await reply(msg, "ℹ️ Không tìm thấy tag cần xóa.")
            return

        # del: mark note as deleted (cross out channel msg)
        if low == "del":
            if note.get("del"):
                await reply(msg, "ℹ️ Ghi chú đã được đánh dấu xóa trước đó.")
                return
            set_del(conn, thread_id, True)
            note["del"] = True
            await edit_channel_message(note)
            await reply(msg, "✅ Đã đánh dấu xóa ghi chú.")
            return

        # check: toggle boolean field
        if low == "check":
            new_check = not note.get("check")
            set_check(conn, thread_id, new_check)
            note["check"] = new_check
            await edit_channel_message(note)
            await reply(msg, f"✅ Đã {'bật' if new_check else 'tắt'} check.")
            return

        # update: manually refresh the main channel message (errors surfaced to user)
        if low == "update":
            try:
                text_out = format_channel_message(note)
                await client.edit_message(
                    int(note.get("channel_id")), int(note.get("message_id")), text_out, parse_mode="html"
                )
                await reply(msg, "✅ Đã cập nhật hiển thị ghi chú.")
            except Exception as e:  # noqa: BLE001
                log.error("Failed to update main note message in channel: %s", e)
                await reply(msg, f"❌ Lỗi cập nhật: {e}")
            return

        # getjson
        if low == "getjson":
            dump = {
                "thread_id": note.get("thread_id"),
                "text": note.get("text"),
                "tags": note.get("tags"),
                "check": note.get("check"),
                "del": note.get("del"),
                "channel_id": note.get("channel_id"),
                "message_id": note.get("message_id"),
                "updated_at": note.get("updated_at"),
            }
            payload = _escape_html(json.dumps(dump, ensure_ascii=False, indent=2))
            await reply(msg, f"<pre>{payload}</pre>", parse_mode="html")
            return
