"""Đẩy 1 bản nháp lên VNPT + vá blob đơn — LÕI DÙNG CHUNG của Lưu và Reset.

Thứ tự BẤT DI BẤT DỊCH: import fkey MỚI trước rồi mới xoá fkey CŨ (updateInvoice
bị VNPT khoá trên TT78 → sửa = tạo lại; import lỗi thì nháp cũ vẫn còn nguyên,
không bao giờ mất nháp). Gọi từ server_app/vnpt_invoice_routes.py; SOAP nằm ở
integrations/vnpt_invoice/.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

from order_db import _save_order, get_order_by_thread_id, transaction

from integrations.vnpt_invoice import build_invoice_xml, compute_totals, delete_draft, import_draft
from integrations.vnpt_invoice import core as vnpt_core
from integrations.vnpt_invoice.core import VnptError

log = logging.getLogger("server")

# Khoá theo đơn — chống 2 request cùng tạo/sửa/reset/xoá nháp của 1 đơn
_locks: dict[int, asyncio.Lock] = {}


def lock(tid: int) -> asyncio.Lock:
    if tid not in _locks:
        if len(_locks) > 1024:
            _locks.clear()
        _locks[tid] = asyncio.Lock()
    return _locks[tid]


async def push_draft(conn, tid: int, *, buyer: dict, lines: list[dict],
                     vat_rate: int, actor: str, old: dict) -> tuple[dict, str | None, dict]:
    """Import nháp MỚI (fkey mới) → xoá nháp cũ → ghi `$.vnpt_invoice`.

    Trả (draft mới, warn, order sau khi ghi). Caller PHẢI đang giữ lock(tid).
    - ValueError: dữ liệu sai (compute_totals) — chưa đụng gì tới VNPT.
    - VnptError: import hỏng — blob KHÔNG đổi, nháp cũ còn nguyên.
    - LookupError: đơn biến mất giữa chừng.
    Xoá nháp cũ hỏng thì KHÔNG raise: nháp mới đã lên, chỉ trả `warn` để văn
    phòng xoá tay bản mồ côi trên portal.
    """
    totals = compute_totals(lines, vat_rate)
    fkey = f"LTP{tid}-{int(time.time() * 1000)}"
    xml = build_invoice_xml(fkey=fkey, buyer=buyer, lines=lines, vat_rate=vat_rate)
    await asyncio.to_thread(import_draft, xml)
    warn = None
    old_fkey = old.get("fkey") if old.get("synced") else None
    if old_fkey:
        try:
            await asyncio.to_thread(delete_draft, old_fkey, missing_ok=True)
        except VnptError as e:
            warn = f"Nháp mới đã tạo nhưng chưa xoá được nháp cũ trên VNPT ({old_fkey}): {e}"
            log.error("vnpt delete old draft failed tid=%s fkey=%s: %s", tid, old_fkey, e)
    now = datetime.now(UTC).isoformat()
    # RE-READ trong transaction SAU await VNPT — chỉ vá key vnpt_invoice.
    # Dựng dict MỚI (không spread `old`) nên published/invoice_no/mtc/
    # missing_on_vnpt cũ tự rụng — fkey mới là nháp mới tinh, chưa phát hành.
    with transaction(conn):
        fresh = get_order_by_thread_id(conn, tid)
        if not fresh:
            raise LookupError("Không tìm thấy đơn")
        draft = {
            "fkey": fkey,
            "pattern": vnpt_core.VNPT_INV_PATTERN,
            "serial": vnpt_core.VNPT_INV_SERIAL,
            "buyer": buyer, "lines": totals["lines"], "vat_rate": vat_rate,
            "goods": totals["goods"], "discount": totals["discount"],
            "total": totals["total"], "vat_amount": totals["vat_amount"],
            "amount": totals["amount"],
            "synced": True,
            "created_at": old.get("created_at") or now,
            "created_by": old.get("created_by") or actor,
            "updated_at": now, "updated_by": actor,
        }
        fresh["vnpt_invoice"] = draft
        _save_order(conn, tid, fresh)
    return draft, warn, fresh
