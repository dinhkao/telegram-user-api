"""On-demand customer debt refresh from KiotViet.

Debt is updated event-driven (invoice create/delete, payment, channel
render) via order_store.update_customer_debt(). This module provides
refresh_single_debt() for the /api/customers/{key}/refresh-debt endpoint.
Connects to: integrations/kiotviet, order_store/customers (app.db).
"""
from __future__ import annotations

import json
import logging
import time

from utils.db import get_connection
from utils.paths import SHARED_DB_PATH

log = logging.getLogger("debt_sync")


def schedule_debt_resync(firebase_key: str, delay: float = 6.0) -> None:
    """Fetch lại debt SAU `delay` giây (nền, không chặn).

    KiotViet cập nhật công nợ khách kiểu eventual-consistency: GET /customers/{id}
    NGAY sau khi tạo hoá đơn/thanh toán có thể vẫn trả debt CŨ (chưa gộp giao dịch
    vừa tạo). Các core đã cập nhật debt tức thì; hàm này lên lịch fetch lại 1 lần nữa
    để bắt giá trị mới → tránh công nợ khách bị trễ 1 nhịp. Gọi từ invoice/payment core.
    """
    if not firebase_key:
        return
    import asyncio

    async def _run():
        try:
            await asyncio.sleep(delay)
            data = await asyncio.to_thread(refresh_single_debt, str(firebase_key))
            if data is not None:
                from server_app.realtime import emit_customer_changed
                emit_customer_changed(str(firebase_key))
        except Exception as e:  # noqa: BLE001 — nền, không được làm hỏng luồng gọi
            log.warning("debt resync failed key=%s: %s", firebase_key, e)

    try:
        from server_app.tasks import spawn_tracked
        spawn_tracked("debt.resync", _run())
    except Exception as e:  # noqa: BLE001 — không có loop (vd script) → bỏ qua
        log.warning("debt resync schedule failed key=%s: %s", firebase_key, e)


def refresh_single_debt(firebase_key: str) -> dict | None:
    """Fetch live debt for one customer from KiotViet. Returns updated data or None."""
    from integrations.kiotviet.customers import get_customer_debt_kv

    conn = get_connection(SHARED_DB_PATH)
    try:
        row = conn.execute(
            "SELECT json FROM customers WHERE firebase_key = ? AND deleted_at IS NULL",
            (firebase_key,),
        ).fetchone()
        if not row:
            return None
        data = json.loads(row["json"])
        kv_id = data.get("kh_id")
        if not kv_id:
            return data
        det = get_customer_debt_kv(int(kv_id))
        new_debt = det.get("debt")
        if new_debt is None:
            return data
        now_ms = int(time.time() * 1000)
        data["debt"] = new_debt
        data["debt_updated_at"] = now_ms
        conn.execute(
            "UPDATE customers SET json = ?, updated_at = ? WHERE firebase_key = ?",
            (json.dumps(data, ensure_ascii=False), now_ms, firebase_key),
        )
        conn.commit()
        return data
    finally:
        conn.close()
