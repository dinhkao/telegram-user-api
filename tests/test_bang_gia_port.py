"""Verification script for command_handlers/bang_gia_commands.py (ported
from final_telegram/bots/groupBangGia.js).

Run: PYTHONPATH=. .venv/bin/python tests/test_bang_gia_port.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace


GROUP_ID = -1002373184927


class FakeMessage:
    _next_id = 1

    def __init__(self, text, chat_id=GROUP_ID, thread_id=None):
        self.text = text
        self.chat_id = chat_id
        self.id = FakeMessage._next_id
        FakeMessage._next_id += 1
        self.reply_to = None
        self.reply_to_top_id = thread_id


class FakeEvent:
    def __init__(self, text, thread_id=None):
        self.message = FakeMessage(text, thread_id=thread_id)


class FakeCreateForumTopicResult:
    def __init__(self, message_id):
        self.updates = [SimpleNamespace(message=SimpleNamespace(id=message_id))]


class FakeClient:
    def __init__(self):
        self.handlers = []
        self.sent = []
        self.calls = []
        self._next_topic_id = 100

    def on(self, _event_builder):
        def decorator(fn):
            self.handlers.append(fn)
            return fn
        return decorator

    async def send_message(self, chat_id, text, reply_to=None, parse_mode=None):
        self.sent.append({"chat_id": chat_id, "text": text, "reply_to": reply_to, "parse_mode": parse_mode})
        return None

    async def __call__(self, request):
        self.calls.append(request)
        cls_name = type(request).__name__
        if cls_name == "CreateForumTopicRequest":
            tid = self._next_topic_id
            self._next_topic_id += 1
            return FakeCreateForumTopicResult(tid)
        if cls_name == "EditForumTopicRequest":
            return SimpleNamespace(updates=[])
        raise AssertionError(f"unexpected request type: {cls_name}")


async def main():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "app.db")
    os.environ["SHARED_DB_PATH"] = db_path
    os.environ["GROUP_BANG_GIA_ID"] = str(GROUP_ID)

    import command_handlers.bang_gia_commands as bgc

    assert bgc.SHARED_DB_PATH == db_path, "module did not pick up SHARED_DB_PATH env override"
    assert bgc.GROUP_BANG_GIA_ID == GROUP_ID, "module did not pick up GROUP_BANG_GIA_ID env override"

    client = FakeClient()
    bgc.register_bang_gia_commands(client)
    assert len(client.handlers) == 1, f"expected 1 handler, got {len(client.handlers)}"
    handler = client.handlers[0]

    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    # 1) new — create forum topic + slip
    await handler(FakeEvent("new"))
    check(len(client.calls) == 1, "new: expected exactly 1 CreateForumTopicRequest call")
    check(len(client.sent) == 1, "new: expected exactly 1 reply sent")
    new_reply = client.sent[-1]
    check("Đã tạo bảng giá mới" in new_reply["text"], "new: missing confirmation text")
    thread_id = 100
    check(f"ID: {thread_id}" in new_reply["text"], "new: missing thread id in confirmation")
    check(new_reply["reply_to"] == thread_id, "new: reply should land in the new topic (reply_to=thread_id)")

    # 2) fix <name> — rename topic
    await handler(FakeEvent("fix Bang gia SP2026", thread_id=thread_id))
    check(len(client.sent) == 2, "fix: expected a reply sent")
    fix_reply = client.sent[-1]
    check("Đã đổi tên: Bang gia SP2026" in fix_reply["text"], "fix: wrong rename confirmation")
    check(any(type(c).__name__ == "EditForumTopicRequest" for c in client.calls), "fix: EditForumTopicRequest not called")

    # 3) <SP> <price> — set price
    await handler(FakeEvent("K2L 5000", thread_id=thread_id))
    check(len(client.sent) == 3, "set price: expected a reply sent")
    set_reply = client.sent[-1]
    check("Cập nhật thành công" in set_reply["text"], "set price: missing success text")
    check("K2L 5.000đ" in set_reply["text"], "set price: wrong vi-grouped price format")

    # 4) <SP> — query price
    await handler(FakeEvent("K2L", thread_id=thread_id))
    check(len(client.sent) == 4, "query price: expected a reply sent")
    query_reply = client.sent[-1]
    check(query_reply["text"] == "K2L: 5.000đ", "query price: wrong query reply text")

    # unknown SP query
    await handler(FakeEvent("ABC", thread_id=thread_id))
    check(client.sent[-1]["text"] == "ABC chưa có giá", "query unknown SP: wrong reply text")

    # 5) show — list current prices
    await handler(FakeEvent("show", thread_id=thread_id))
    check(len(client.sent) == 6, "show: expected a reply sent")
    show_reply = client.sent[-1]
    check("Bảng giá hiện tại:" in show_reply["text"], "show: missing header")
    check("K2L 5.000đ" in show_reply["text"], "show: missing K2L entry")

    # 6) copy — print the get_price_list helper command
    await handler(FakeEvent("copy", thread_id=thread_id))
    check(len(client.sent) == 7, "copy: expected a reply sent")
    copy_reply = client.sent[-1]
    check(copy_reply["text"] == f"`get_price_list {thread_id}`", "copy: wrong helper command text")
    check(copy_reply["parse_mode"] == "md", "copy: expected parse_mode md")

    # messages outside any topic (no thread_id) are ignored for SP/copy/show/fix-without-thread
    before = len(client.sent)
    await handler(FakeEvent("copy"))
    check(len(client.sent) == before, "copy without thread_id: should not reply")
    await handler(FakeEvent("show"))
    check(len(client.sent) == before, "show without thread_id: should not reply")
    await handler(FakeEvent("K2L"))
    check(len(client.sent) == before, "SP query without thread_id: should not reply")

    if failures:
        print("FAILED:")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    else:
        print(f"PASS: all assertions passed ({len(client.sent)} messages sent)")


if __name__ == "__main__":
    asyncio.run(main())
