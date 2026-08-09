"""Dò HĐ KiotViet "mồ côi" sau khi POST /invoices lỗi (thường là timeout).

KiotViet có thể đã tạo HĐ xong nhưng response không về kịp → app báo lỗi, đơn
không có kiotvietInvoiceID, bấm Tạo HĐ lại là ra HĐ TRÙNG (đã xảy ra 2026-08-09
với HD085869). Ở đây: hỏi lại KiotViet danh sách HĐ gần nhất của khách, so khớp
với các dòng vừa gửi (integrations/kiotviet/recover — logic thuần), loại các id
đã gắn vào đơn khác, rồi trả HĐ đó về cho luồng tạo HĐ dùng tiếp như bình thường.

Nối: integrations.kiotviet (API + so khớp), order_db (bảng orders).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

log = logging.getLogger("server")


def _used_invoice_ids(conn, ids: list[int]) -> set[int]:
    """Trong `ids`, id nào ĐÃ gắn vào một đơn nào đó (không được nhận lại)."""
    if not ids:
        return set()
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT CAST(json_extract(json, '$.kiotvietInvoiceID') AS INTEGER) AS kv "
        f"FROM orders WHERE kv IN ({marks})", [int(i) for i in ids]).fetchall()
    return {int(r[0]) for r in rows if r[0] is not None}


async def find_orphan_invoice(conn, customer_kv_id: int, sent_details: list[dict],
                              since: datetime) -> dict | None:
    """HĐ khách vừa được tạo khớp `sent_details` mà chưa gắn đơn nào → dict HĐ
    (như create_kiotviet_invoice trả), không tìm thấy → None. Nuốt mọi lỗi (đang
    ở nhánh xử lý lỗi — hỏng thêm ở đây thì che mất lỗi gốc)."""
    try:
        from integrations.kiotviet import list_customer_invoices
        from integrations.kiotviet.recover import pick_orphan
        invoices = await asyncio.to_thread(list_customer_invoices, int(customer_kv_id), 20)
        ids = []
        for inv in invoices or []:
            try:
                ids.append(int(inv.get("id")))
            except (TypeError, ValueError):
                pass
        used = _used_invoice_ids(conn, ids)
        return pick_orphan(invoices, sent_details=sent_details, since=since, used_ids=used)
    except Exception as e:  # noqa: BLE001
        log.error("dò HĐ mồ côi lỗi (khách %s): %s", customer_kv_id, e)
        return None
