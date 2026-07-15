"""KiotViet calls phải chạy OFF event loop (asyncio.to_thread) — 1 request KiotViet
CHẬM/treo KHÔNG được đóng băng các client khác.

Regression cho bug "1 KiotViet hang khoá tất cả client": giả lập KiotViet chậm
(time.sleep trong hàm blocking) và đo heartbeat của event loop trong lúc gọi. Nếu
call chạy trên loop → heartbeat đứng im (~0 tick); off-loop → heartbeat vẫn chạy.
"""
import asyncio
import time

import command_handlers.order_commands_v2_delete as v2del


async def _heartbeat(ticks, stop):
    while not stop.is_set():
        await asyncio.sleep(0.01)
        ticks[0] += 1


def test_fetch_old_debt_keeps_loop_responsive(monkeypatch):
    monkeypatch.setattr(v2del, "get_customer_by_key", lambda conn, k: {"kh_id": 123})

    def slow_kv(kv_id):
        time.sleep(0.25)   # giả lập KiotViet CHẬM (blocking urllib)
        return {"debt": 5000}
    monkeypatch.setattr(v2del, "get_customer_debt_kv", slow_kv)

    async def go():
        ticks = [0]
        stop = asyncio.Event()
        hb = asyncio.create_task(_heartbeat(ticks, stop))
        debt = await v2del._fetch_old_debt(object(), "kfb")
        stop.set()
        await hb
        return debt, ticks[0]

    debt, ticks = asyncio.run(go())
    assert debt == 5000
    # KV chậm 0.25s: chặn loop → heartbeat ~0 tick; off-loop → nhiều tick (~25).
    assert ticks >= 12, f"event loop bị CHẶN khi gọi KiotViet (chỉ {ticks} tick)"


def test_delete_kv_invoice_keeps_loop_responsive(monkeypatch):
    def slow_delete(invoice_id):
        time.sleep(0.2)
        return True
    monkeypatch.setattr(v2del, "delete_invoice_kv", slow_delete)

    async def go():
        ticks = [0]
        stop = asyncio.Event()
        hb = asyncio.create_task(_heartbeat(ticks, stop))
        ok, err = await v2del._delete_kv_invoice(999)
        stop.set()
        await hb
        return ok, ticks[0]

    ok, ticks = asyncio.run(go())
    assert ok is True
    assert ticks >= 10, f"event loop bị CHẶN khi xoá HĐ KiotViet (chỉ {ticks} tick)"
