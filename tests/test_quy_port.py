"""Verification script for command_handlers/quy_commands.py (ported from
final_telegram/bots/groupQuy.js).

Run: PYTHONPATH=. .venv/bin/python tests/test_quy_port.py
"""
from __future__ import annotations

import asyncio
import sys


class FakeMessage:
    _next_id = 1

    def __init__(self, text, chat_id=-1002420020918):
        self.text = text
        self.chat_id = chat_id
        self.id = FakeMessage._next_id
        FakeMessage._next_id += 1


class FakeSender:
    def __init__(self, first_name="Nguyen", last_name="Van A"):
        self.first_name = first_name
        self.last_name = last_name


class FakeEvent:
    def __init__(self, text, sender=None):
        self.message = FakeMessage(text)
        self._sender = sender or FakeSender()

    async def get_sender(self):
        return self._sender


class FakeClient:
    def __init__(self):
        self.handlers = []
        self.sent = []

    def on(self, _event_builder):
        def decorator(fn):
            self.handlers.append(fn)
            return fn
        return decorator

    async def send_message(self, chat_id, text, reply_to=None, parse_mode=None):
        self.sent.append({"chat_id": chat_id, "text": text, "reply_to": reply_to, "parse_mode": parse_mode})
        return None


async def main():
    client = FakeClient()

    # in-memory fund receipt store, monkeypatched into the module namespace
    import command_handlers.quy_commands as qc

    store = {}

    def fake_set_fund_receipt(receipt_id, data):
        store[receipt_id] = data
        return True

    def fake_get_fund_receipts():
        return dict(store)

    qc.set_fund_receipt = fake_set_fund_receipt
    qc.get_fund_receipts = fake_get_fund_receipts

    qc.register_quy_commands(client)
    assert len(client.handlers) == 1, f"expected 1 handler, got {len(client.handlers)}"
    handler = client.handlers[0]

    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    # 1) help command
    await handler(FakeEvent("?"))
    check(len(client.sent) == 1, "help: expected exactly 1 message sent")
    check("DANH SÁCH LỆNH" in client.sent[-1]["text"], "help: missing help text")
    check(client.sent[-1]["parse_mode"] == "md", "help: expected parse_mode md")

    # 2) THU
    # (receipt id = epoch-ms as string, mirroring node's Date.now(); sleep a
    # touch between calls so successive receipts don't collide on the same ms)
    await handler(FakeEvent("+500000 thu tien hang"))
    check(len(client.sent) == 2, "thu: expected a notification sent")
    thu_text = client.sent[-1]["text"]
    check("PHIẾU THU QUỸ MỚI" in thu_text, "thu: missing header")
    check("Số tiền: +500.000đ" in thu_text, "thu: wrong amount/sign format")
    check("Lý do: thu tien hang" in thu_text, "thu: wrong reason")
    check("Tổng quỹ hôm nay:" in thu_text, "thu: missing today-total line")
    check("Tổng quỹ hôm nay: 500.000đ" in thu_text, "thu: wrong today total after first receipt")
    check(len(store) == 1, "thu: receipt not saved to store")
    saved_thu = list(store.values())[0]
    check(saved_thu["type"] == "thu", "thu: wrong stored type")
    check(saved_thu["amount"] == 500000, "thu: wrong stored amount")
    check(saved_thu["source"] == "manual", "thu: wrong stored source")
    check(saved_thu["createdBy"] == "Nguyen Van A", "thu: wrong createdBy")

    # 3) CHI
    await asyncio.sleep(0.005)
    await handler(FakeEvent("-200000 ship"))
    check(len(client.sent) == 3, "chi: expected a notification sent")
    chi_text = client.sent[-1]["text"]
    check("PHIẾU CHI QUỸ MỚI" in chi_text, "chi: missing header")
    check("Số tiền: -200.000đ" in chi_text, "chi: wrong amount/sign format")
    check("Lý do: ship" in chi_text, "chi: wrong reason")
    # today total = 500000 - 200000 = 300000
    check("Tổng quỹ hôm nay: 300.000đ" in chi_text, "chi: wrong today total after 2nd receipt")
    check(len(store) == 2, "chi: receipt not saved to store")

    # implicit '+' form (bare int)
    await asyncio.sleep(0.005)
    await handler(FakeEvent("100000 thu khac"))
    check(len(client.sent) == 4, "bare-int thu: expected a notification sent")
    bare_text = client.sent[-1]["text"]
    check("PHIẾU THU QUỸ MỚI" in bare_text, "bare-int thu: should be treated as THU")
    check("Số tiền: +100.000đ" in bare_text, "bare-int thu: wrong sign/amount")

    # 4) ignored message
    before = len(client.sent)
    await handler(FakeEvent("abc"))
    check(len(client.sent) == before, "ignored: 'abc' should not send anything")
    check(len(store) == 3, "ignored: store should be unchanged")

    if failures:
        print("FAILED:")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    else:
        print(f"OK: all assertions passed ({len(client.sent)} messages sent, {len(store)} receipts stored)")


if __name__ == "__main__":
    asyncio.run(main())
