"""Chống tạo HĐ KiotViet TRÙNG (bấm 2 lần / 2 request đồng thời).

Kiểm 2 lớp bảo vệ của order_commands_v3._process_create_invoice_core:
  1. GUARD idempotent: đơn đã có kiotvietInvoiceID → từ chối, KHÔNG gọi KiotViet.
  2. KHOÁ theo đơn (_invoice_create_lock): serialize create cùng 1 đơn (đóng khe
     TOCTOU giữa create_kiotviet_invoice và _save_order).
"""
import asyncio

import order_commands_v3 as oc


def test_guard_rejects_when_invoice_already_exists(monkeypatch):
    # đơn ĐÃ có HĐ KiotViet → bấm tạo lần nữa phải bị chặn, KiotViet không bị gọi
    order = {"thread_id": 1, "invoice": [{"sp": "X", "sl": 1, "price": 1000}],
             "khach_hang_id": "k", "kiotvietInvoiceID": 999}
    called = {"n": 0}
    monkeypatch.setattr(oc, "_get_connection", lambda: object())
    monkeypatch.setattr(oc, "get_order_by_thread_id", lambda conn, tid: order)

    def _fake_create(**kw):
        called["n"] += 1
        return {"id": 111, "code": "HD111"}
    monkeypatch.setattr(oc, "create_kiotviet_invoice", _fake_create)

    res = asyncio.run(oc._process_create_invoice_core(1, None))
    assert res["success"] is False
    assert "đã có" in (res["error"] or "").lower()
    assert called["n"] == 0   # KHÔNG gọi KiotViet


def test_lock_is_per_order_and_serializes():
    async def go():
        assert oc._invoice_create_lock(1) is oc._invoice_create_lock(1)   # cùng đơn = cùng khoá
        assert oc._invoice_create_lock(1) is not oc._invoice_create_lock(2)   # khác đơn = khoá khác

        seq = []

        async def worker(tag, delay):
            async with oc._invoice_create_lock(77):
                seq.append(f"start-{tag}")
                await asyncio.sleep(delay)
                seq.append(f"end-{tag}")

        await asyncio.gather(worker("A", 0.02), worker("B", 0.0))
        # KHÔNG lồng: mỗi start theo ngay bởi end cùng tag (serialize)
        assert seq[0].startswith("start-") and seq[1] == "end-" + seq[0].split("-")[1]
        assert seq[2].startswith("start-") and seq[3] == "end-" + seq[2].split("-")[1]

    asyncio.run(go())


def test_concurrent_create_makes_only_one_invoice(monkeypatch):
    # 2 request tạo HĐ ĐỒNG THỜI cho cùng đơn → KiotViet chỉ bị gọi 1 lần,
    # request kia thấy HĐ vừa lưu → bị guard chặn.
    store = {"order": {"thread_id": 5, "invoice": [{"sp": "X", "sl": 1, "price": 1000}],
                       "khach_hang_id": "k"}}
    calls = {"create": 0}

    monkeypatch.setattr(oc, "_get_connection", lambda: object())
    monkeypatch.setattr(oc, "get_order_by_thread_id", lambda conn, tid: dict(store["order"]))
    monkeypatch.setattr(oc, "get_customer_by_key", lambda conn, k: {"kh_id": 123, "name": "K"})

    def _fake_create(**kw):
        calls["create"] += 1
        return {"id": 900 + calls["create"], "code": f"HD{calls['create']}"}
    monkeypatch.setattr(oc, "create_kiotviet_invoice", _fake_create)
    # nợ cũ chạy trong executor → tạo khe await giữa create và save (nơi TOCTOU xảy ra)
    monkeypatch.setattr(oc, "get_customer_debt_kv", lambda kv_id: {"debt": 0})

    def _fake_save(conn, tid, order):
        store["order"] = dict(order)   # lưu lại → request sau đọc thấy kiotvietInvoiceID
        return True
    monkeypatch.setattr(oc, "_save_order", _fake_save)
    monkeypatch.setattr(oc, "set_task_status", lambda *a, **k: None)

    import product_store
    monkeypatch.setattr(product_store, "kv_ids_for_items", lambda conn, inv: {})
    import order_db
    monkeypatch.setattr(order_db, "update_customer_debt", lambda *a, **k: None)
    import server_app.realtime as rt
    monkeypatch.setattr(rt, "emit_order_changed", lambda *a, **k: None)
    monkeypatch.setattr(rt, "emit_customer_changed", lambda *a, **k: None)
    import server_app.debt_sync as ds
    monkeypatch.setattr(ds, "schedule_debt_resync", lambda *a, **k: None)

    async def go():
        r1, r2 = await asyncio.gather(
            oc._process_create_invoice_core(5, None),
            oc._process_create_invoice_core(5, None),
        )
        return r1, r2

    r1, r2 = asyncio.run(go())
    assert calls["create"] == 1   # KiotViet CHỈ bị gọi 1 lần
    oks = [r for r in (r1, r2) if r["success"]]
    rejected = [r for r in (r1, r2) if not r["success"]]
    assert len(oks) == 1 and len(rejected) == 1
    assert "đã có" in (rejected[0]["error"] or "").lower()
