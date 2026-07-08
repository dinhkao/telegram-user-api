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


def _ts(v) -> float:
    """ISO / epoch (s|ms) → epoch giây (0 nếu rỗng) — so cửa sổ loạt phiếu thu."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        x = float(v)
        return x / 1000.0 if x > 1e12 else x
    s = str(v).strip()
    if not s:
        return 0.0
    try:
        from datetime import datetime
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def derive_batch_new_debt(amounts: list, kv_debt) -> list | None:
    """[amount phiếu thu theo thời gian TĂNG] + nợ KV cuối → new_debt từng phiếu.

    Phiếu CUỐI = số KV; phiếu trước = new_debt phiếu sau + amount phiếu sau
    (phân bổ 1 số thật ngược lên, không tính nợ ngoài KV). None nếu lòi số âm —
    dấu hiệu có HĐ chen giữa loạt → không phân bổ (chỉ vá phiếu cuối). Pure, có test.
    """
    out = [0.0] * len(amounts)
    run = float(kv_debt)
    for i in range(len(amounts) - 1, -1, -1):
        out[i] = run
        run += float(amounts[i] or 0)
    return None if any(v < -1.0 for v in out) else out


_BATCH_WINDOW_S = 180.0   # loạt = các phiếu thu trong 3 phút gần nhất


def _patch_batch_new_debt(firebase_key: str, kv_debt) -> list[int]:
    """Vá nợ SAU cho LOẠT phiếu thu gần đây (≤3 phút) của khách bằng 1 số KV mới.

    Thu nhiều phiếu liền tay → resync +6s của TỪNG phiếu đều đọc ra cùng số nợ
    CUỐI từ KiotViet → mọi phiếu bị ghi trùng số cuối (sai). Sửa: neo số KV vào
    phiếu CUỐI, phân bổ ngược lên các phiếu trước (derive_batch_new_debt). Loạt
    1 phiếu = hành vi cũ (vá đúng phiếu đó). Trả list thread_id có blob đổi.
    """
    import time as _time
    from order_db import _get_connection, get_order_by_thread_id, _save_order
    from order_store.schema import transaction
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT o.thread_id tid, json_extract(p.value,'$.id') pid,"
            " json_extract(p.value,'$.amount') amt, json_extract(p.value,'$.created_at') at"
            " FROM orders o, json_each(o.json,'$.payments') p"
            " WHERE CAST(json_extract(o.json,'$.khach_hang_id') AS TEXT) = ?"
            " AND o.deleted_at IS NULL",
            (str(firebase_key),)).fetchall()
        cutoff = _time.time() - _BATCH_WINDOW_S
        batch = sorted(
            ({"tid": r["tid"], "pid": r["pid"], "amt": float(r["amt"] or 0), "ts": _ts(r["at"])}
             for r in rows if r["pid"] and _ts(r["at"]) >= cutoff),
            key=lambda x: x["ts"])
        if not batch:
            return []
        targets = derive_batch_new_debt([b["amt"] for b in batch], kv_debt)
        if targets is None:   # có HĐ chen giữa loạt → chỉ vá phiếu cuối như cũ
            batch, targets = batch[-1:], [float(kv_debt)]
        want = {}   # thread_id → {payment_id: new_debt}
        for b, nd in zip(batch, targets):
            want.setdefault(b["tid"], {})[b["pid"]] = nd
        changed_tids: list[int] = []
        for tid, by_pid in want.items():
            with transaction(conn):
                order = get_order_by_thread_id(conn, int(tid))
                if not order:
                    continue
                changed = False
                for p in order.get("payments", []):
                    nd = by_pid.get(p.get("id"))
                    if nd is not None and p.get("new_debt") != nd:
                        p["new_debt"] = nd
                        changed = True
                if changed:
                    _save_order(conn, int(tid), order)
                    changed_tids.append(int(tid))
        return changed_tids
    finally:
        conn.close()


def schedule_debt_resync(firebase_key: str, delay: float = 6.0,
                         thread_id: int | None = None, payment_id: str | None = None) -> None:
    """Fetch lại debt SAU `delay` giây (nền, không chặn).

    KiotViet cập nhật công nợ khách kiểu eventual-consistency: GET /customers/{id}
    NGAY sau khi tạo hoá đơn/thanh toán có thể vẫn trả debt CŨ (chưa gộp giao dịch
    vừa tạo). Các core đã cập nhật debt tức thì; hàm này lên lịch fetch lại 1 lần nữa
    (VẪN từ KiotViet, không tính tay) để bắt giá trị mới → tránh công nợ khách bị trễ.
    Nếu có thread_id+payment_id (resync do PHIẾU THU) → vá nợ SAU cho cả LOẠT phiếu
    thu gần đây (_patch_batch_new_debt — thu liền tay nhiều phiếu chỉ có 1 số KV
    cuối, phân bổ ngược). Gọi từ invoice/payment core.
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
                if thread_id and payment_id and data.get("debt") is not None:
                    changed = await asyncio.to_thread(_patch_batch_new_debt, str(firebase_key), data.get("debt"))
                    from server_app.realtime import emit_order_changed
                    for tid in changed:
                        emit_order_changed(tid)
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
