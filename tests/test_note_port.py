"""Verification script for command_handlers/note_commands.py (ported from
final_telegram/bots/groupNote.js).

Run: PYTHONPATH=. .venv/bin/python tests/test_note_port.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import tempfile

# SHARED_DB_PATH is read at module-import time by command_handlers.note_commands,
# so point it at a throwaway temp DB *before* importing that module.
_TMPDIR = tempfile.mkdtemp()
_DB_PATH = os.path.join(_TMPDIR, "test_note.db")
os.environ["SHARED_DB_PATH"] = _DB_PATH

import command_handlers.note_commands as nc  # noqa: E402
from note_store import create_note_table, get_note  # noqa: E402

GROUP_NOTE_ID = nc.GROUP_NOTE_ID
THREAD_ID = 999
CHANNEL_ID = -1001234567890
MESSAGE_ID = 777


class FakeMessage:
    _next_id = 1

    def __init__(self, text, chat_id=GROUP_NOTE_ID, thread_id=THREAD_ID, sender_id=111):
        self.text = text
        self.chat_id = chat_id
        self.id = FakeMessage._next_id
        FakeMessage._next_id += 1
        self.sender_id = sender_id
        # extract_thread_id() checks .reply_to first, then falls back to this
        self.reply_to = None
        self.reply_to_top_id = thread_id


class FakeEvent:
    def __init__(self, text, thread_id=THREAD_ID):
        self.message = FakeMessage(text, thread_id=thread_id)


class FakeClient:
    def __init__(self):
        self.handlers = []
        self.sent = []
        self.edits = []
        self.raw_calls = []

    def on(self, _event_builder):
        def decorator(fn):
            self.handlers.append(fn)
            return fn
        return decorator

    async def send_message(self, chat_id, text, reply_to=None, parse_mode=None):
        self.sent.append({"chat_id": chat_id, "text": text, "reply_to": reply_to, "parse_mode": parse_mode})
        return None

    async def edit_message(self, chat_id, message_id, text, parse_mode=None):
        self.edits.append({"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": parse_mode})
        return None

    async def __call__(self, request):
        # fake for `await client(EditForumTopicRequest(...))`
        self.raw_calls.append(request)
        return None


def _seed_note():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    create_note_table(conn)
    conn.execute(
        "INSERT INTO notes (thread_id, text, tags, check_flag, del_flag, channel_id, message_id, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        (THREAD_ID, "old text", json.dumps(["#foo"]), 0, 0, CHANNEL_ID, MESSAGE_ID),
    )
    conn.commit()
    conn.close()


async def main():
    _seed_note()

    client = FakeClient()
    nc.register_note_commands(client)
    assert len(client.handlers) == 1, f"expected 1 handler, got {len(client.handlers)}"
    handler = client.handlers[0]

    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    def fresh_note():
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        note = get_note(conn, THREAD_ID)
        conn.close()
        return note

    # 1) fix hello
    await handler(FakeEvent("fix hello"))
    check(len(client.sent) == 1, "fix: expected exactly 1 reply")
    check(client.sent[-1]["text"] == "✅ Đã cập nhật nội dung ghi chú.", "fix: wrong ack text")
    check(len(client.raw_calls) == 1, "fix: expected topic rename call (EditForumTopicRequest)")
    check(getattr(client.raw_calls[-1], "title", None) == "hello", "fix: topic rename title mismatch")
    check(len(client.edits) == 1, "fix: expected channel message edit")
    check(client.edits[-1]["chat_id"] == CHANNEL_ID and client.edits[-1]["message_id"] == MESSAGE_ID,
          "fix: channel edit target mismatch")
    check("hello" in client.edits[-1]["text"], "fix: channel edit text should contain new text")
    n = fresh_note()
    check(n["text"] == "hello", f"fix: DB text not updated, got {n['text']!r}")

    # 2) add tag urgent
    await handler(FakeEvent("add tag urgent"))
    check(len(client.sent) == 2, "add tag: expected exactly 1 new reply")
    check(client.sent[-1]["text"] == "✅ Đã thêm tag: urgent", "add tag: wrong ack text")
    n = fresh_note()
    check(n["tags"] == ["#foo", "#urgent"], f"add tag: DB tags wrong, got {n['tags']}")
    check(len(client.edits) == 2, "add tag: expected channel message edit")

    # 2b) add tag urgent again -> idempotent
    await handler(FakeEvent("add tag urgent"))
    check(client.sent[-1]["text"] == "ℹ️ Tag đã tồn tại, không có gì thay đổi.", "add tag (dup): wrong ack text")
    n = fresh_note()
    check(n["tags"] == ["#foo", "#urgent"], "add tag (dup): tags should be unchanged")

    # 3) check (toggle on)
    await handler(FakeEvent("check"))
    check(client.sent[-1]["text"] == "✅ Đã bật check.", "check: wrong ack text")
    n = fresh_note()
    check(n["check"] is True, "check: DB check_flag not set")
    check(len(client.edits) == 4, "check: expected channel message edit")
    check("✅" in client.edits[-1]["text"], "check: channel message should show check ✅")

    # 4) del
    await handler(FakeEvent("del"))
    check(client.sent[-1]["text"] == "✅ Đã đánh dấu xóa ghi chú.", "del: wrong ack text")
    n = fresh_note()
    check(n["del"] is True, "del: DB del_flag not set")
    check("<s>" in client.edits[-1]["text"], "del: channel message should be struck through")

    # 4b) del again -> idempotent message
    await handler(FakeEvent("del"))
    check(client.sent[-1]["text"] == "ℹ️ Ghi chú đã được đánh dấu xóa trước đó.", "del (dup): wrong ack text")

    # 5) getjson
    edits_before = len(client.edits)
    await handler(FakeEvent("getjson"))
    check(client.sent[-1]["parse_mode"] == "html", "getjson: expected html parse_mode")
    check(client.sent[-1]["text"].startswith("<pre>") and client.sent[-1]["text"].endswith("</pre>"),
          "getjson: expected <pre> wrapper")
    dumped = json.loads(client.sent[-1]["text"][len("<pre>"):-len("</pre>")])
    check(dumped["text"] == "hello", "getjson: wrong text in dump")
    check(dumped["tags"] == ["#foo", "#urgent"], "getjson: wrong tags in dump")
    check(dumped["check"] is True, "getjson: wrong check in dump")
    check(dumped["del"] is True, "getjson: wrong del in dump")
    check(len(client.edits) == edits_before, "getjson: should not edit the channel message")

    # 6) ? help
    await handler(FakeEvent("?"))
    check(client.sent[-1]["parse_mode"] == "md", "help: expected md parse_mode")
    check("Ghi chú" in client.sent[-1]["text"], "help: missing help text")

    # 7) unknown note (thread has no seeded row) -> silent, no reply/edit
    sent_before, edits_before = len(client.sent), len(client.edits)
    await handler(FakeEvent("fix should be ignored", thread_id=424242))
    check(len(client.sent) == sent_before, "unknown thread: fix should be silently ignored")
    check(len(client.edits) == edits_before, "unknown thread: no channel edit expected")

    if failures:
        print("FAILED:")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    else:
        print(f"OK: all assertions passed ({len(client.sent)} messages sent, {len(client.edits)} channel edits, "
              f"{len(client.raw_calls)} topic renames)")


if __name__ == "__main__":
    asyncio.run(main())
