"""API hoá đơn NHÁP VNPT cho webapp — GET/POST/DELETE /api/order/{tid}/vnpt-invoice.

Độc lập hoàn toàn với HĐ KiotViet (Duy chốt 2026-08-26). POST = tạo HOẶC sửa:
luôn import nháp MỚI (fkey mới) lên VNPT trước rồi mới xoá nháp cũ — thứ tự này
để không bao giờ mất nháp nếu import lỗi (updateInvoice bị VNPT khoá trên TT78).
Ghi blob đơn `$.vnpt_invoice` + cache khách `$.vnpt_profile` (order_store/
customers). Quyền: xem/tạo/sửa = văn phòng, xoá = admin. Logic thuần ở
server_app/vnpt_invoice_domain.py; SOAP ở integrations/vnpt_invoice/.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

from aiohttp import web

from order_db import _get_connection, _save_order, get_customer_by_key, get_order_by_thread_id, transaction
from order_store.customers import update_customer

from integrations.vnpt_invoice import build_invoice_xml, compute_totals, delete_draft, import_draft
from integrations.vnpt_invoice import core as vnpt_core
from integrations.vnpt_invoice.core import VnptError
from server_app.vnpt_invoice_domain import build_prefill, normalize_body, updated_profile

log = logging.getLogger("server")

# Khoá theo đơn — chống 2 request cùng tạo/sửa/xoá nháp 1 đơn (như _invoice_create_lock)
_locks: dict[int, asyncio.Lock] = {}


def _lock(tid: int) -> asyncio.Lock:
    if tid not in _locks:
        if len(_locks) > 1024:
            _locks.clear()
        _locks[tid] = asyncio.Lock()
    return _locks[tid]


def _tid(request: web.Request) -> int | None:
    raw = request.match_info.get("thread_id", "").strip()
    return int(raw) if raw.lstrip("-").isdigit() else None


def _err(msg: str, status: int = 400) -> web.Response:
    return web.json_response({"ok": False, "error": msg}, status=status)


def _customer_key(order: dict) -> str | None:
    key = order.get("khach_hang_id") or order.get("khID")
    return str(key) if key else None


def _units_by_spid(conn, order: dict) -> dict[int, str]:
    ids = sorted({int(it["sp_id"]) for it in order.get("invoice") or []
                  if it.get("sp_id")})
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    rows = conn.execute(f"SELECT id, unit FROM products WHERE id IN ({marks})", ids).fetchall()
    return {int(r["id"]): str(r["unit"] or "") for r in rows}


async def vnpt_invoice_get_handler(request: web.Request):
    """Nháp hiện có (blob) + prefill (cache khách ⊕ dòng hàng đơn ⊕ danh mục SP)."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return _err("Chỉ văn phòng mới xem được HĐ điện tử", 403)
    tid = _tid(request)
    if tid is None:
        return _err("thread_id không hợp lệ")
    conn = _get_connection()
    order = get_order_by_thread_id(conn, tid)
    if not order:
        return _err("Không tìm thấy đơn", 404)
    customer = None
    kh_key = _customer_key(order)
    if kh_key:
        customer = get_customer_by_key(conn, kh_key)
    prefill = build_prefill(order, customer, _units_by_spid(conn, order))
    return web.json_response({
        "ok": True,
        "configured": vnpt_core.configured(),
        "pattern": vnpt_core.VNPT_INV_PATTERN,
        "serial": vnpt_core.VNPT_INV_SERIAL,
        "draft": order.get("vnpt_invoice"),
        "prefill": prefill,
    })


async def vnpt_invoice_save_handler(request: web.Request):
    """Tạo/sửa nháp: import fkey MỚI lên VNPT → xoá fkey cũ → ghi blob + cache khách."""
    from server_app.order_api_common import apply_web_actor, is_office_request
    try:
        body = await request.json()
    except Exception:
        return _err("Invalid JSON")
    apply_web_actor(request, body)
    if not await is_office_request(request):
        return _err("Chỉ văn phòng mới được tạo/sửa HĐ điện tử nháp", 403)
    tid = _tid(request)
    if tid is None:
        return _err("thread_id không hợp lệ")
    try:
        buyer, lines, vat_rate = normalize_body(body)
    except ValueError as e:
        return _err(str(e))
    conn = _get_connection()
    if not get_order_by_thread_id(conn, tid):
        return _err("Không tìm thấy đơn", 404)
    totals = compute_totals(lines, vat_rate)
    fkey = f"LTP{tid}-{int(time.time() * 1000)}"
    xml = build_invoice_xml(fkey=fkey, buyer=buyer, lines=lines, vat_rate=vat_rate)
    actor = str(request.get("web_user") or body.get("user_id") or "?")
    async with _lock(tid):
        old = (get_order_by_thread_id(conn, tid) or {}).get("vnpt_invoice") or {}
        old_fkey = old.get("fkey") if old.get("synced") else None
        try:
            await asyncio.to_thread(import_draft, xml)
        except VnptError as e:
            return _err(f"VNPT từ chối: {e}", 502)
        warn = None
        if old_fkey:
            try:
                await asyncio.to_thread(delete_draft, old_fkey, missing_ok=True)
            except VnptError as e:
                # Nháp MỚI đã lên — chỉ còn nháp cũ mồ côi trên VNPT, báo để xoá tay
                warn = f"Nháp mới đã tạo nhưng chưa xoá được nháp cũ trên VNPT ({old_fkey}): {e}"
                log.error("vnpt delete old draft failed tid=%s fkey=%s: %s", tid, old_fkey, e)
        now = datetime.now(UTC).isoformat()
        # RE-READ trong transaction SAU await VNPT — chỉ vá key vnpt_invoice
        with transaction(conn):
            fresh = get_order_by_thread_id(conn, tid)
            if not fresh:
                return _err("Không tìm thấy đơn", 404)
            fresh["vnpt_invoice"] = {
                "fkey": fkey,
                "pattern": vnpt_core.VNPT_INV_PATTERN,
                "serial": vnpt_core.VNPT_INV_SERIAL,
                "buyer": buyer, "lines": totals["lines"], "vat_rate": vat_rate,
                "total": totals["total"], "vat_amount": totals["vat_amount"],
                "amount": totals["amount"],
                "synced": True,
                "created_at": old.get("created_at") or now,
                "created_by": old.get("created_by") or actor,
                "updated_at": now, "updated_by": actor,
            }
            _save_order(conn, tid, fresh)
        kh_key = _customer_key(fresh)
        if kh_key:
            cust = get_customer_by_key(conn, kh_key)
            if cust is not None:
                cust["vnpt_profile"] = updated_profile(cust.get("vnpt_profile"), buyer, lines, vat_rate)
                update_customer(conn, kh_key, cust)
    from audit_log import async_log_event
    from server_app.realtime import emit_order_changed
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.vnpt_draft", async_log_event(
        "order.vnpt_draft_saved", actor_type="web", actor_id=actor, thread_id=tid,
        payload={"fkey": fkey, "amount": totals["amount"], "vat_rate": vat_rate,
                 "line_count": len(lines), "created": not old}))
    emit_order_changed(tid)
    return web.json_response({"ok": True, "fkey": fkey, "amount": totals["amount"],
                              "warn": warn})


async def vnpt_invoice_delete_handler(request: web.Request):
    """Xoá nháp (VNPT + blob) — CHỈ admin, như xoá HĐ KiotViet."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return _err("Chỉ admin mới được xoá HĐ điện tử nháp", 403)
    tid = _tid(request)
    if tid is None:
        return _err("thread_id không hợp lệ")
    conn = _get_connection()
    async with _lock(tid):
        order = get_order_by_thread_id(conn, tid)
        if not order:
            return _err("Không tìm thấy đơn", 404)
        draft = order.get("vnpt_invoice")
        if not draft:
            return _err("Đơn không có HĐ điện tử nháp")
        if draft.get("synced") and draft.get("fkey"):
            try:
                await asyncio.to_thread(delete_draft, draft["fkey"], missing_ok=True)
            except VnptError as e:
                return _err(f"Lỗi xoá nháp trên VNPT: {e}", 502)
        with transaction(conn):
            fresh = get_order_by_thread_id(conn, tid)
            if fresh and fresh.pop("vnpt_invoice", None) is not None:
                _save_order(conn, tid, fresh)
    actor = str(request.get("web_user") or "?")
    from audit_log import async_log_event
    from server_app.realtime import emit_order_changed
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.vnpt_draft_del", async_log_event(
        "order.vnpt_draft_deleted", actor_type="web", actor_id=actor, thread_id=tid,
        payload={"fkey": draft.get("fkey"), "amount": draft.get("amount")}))
    emit_order_changed(tid)
    return web.json_response({"ok": True})


async def vnpt_invoice_pdf_handler(request: web.Request):
    """GET .../vnpt-invoice/pdf — tải PDF bản thể hiện nháp từ VNPT (văn phòng).
    Mở tab mới kèm ?token= như invoice-html; Số HĐ trên PDF = 00000000 (chưa phát hành)."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.Response(text="Chỉ văn phòng mới tải được PDF HĐ điện tử", status=403)
    tid = _tid(request)
    if tid is None:
        return web.Response(text="thread_id không hợp lệ", status=400)
    conn = _get_connection()
    order = get_order_by_thread_id(conn, tid)
    if not order:
        return web.Response(text="Không tìm thấy đơn", status=404)
    draft = order.get("vnpt_invoice") or {}
    if not (draft.get("synced") and draft.get("fkey")):
        return web.Response(text="Đơn chưa có HĐ điện tử nháp — tạo nháp trước.", status=400)
    from integrations.vnpt_invoice import download_draft_pdf
    try:
        pdf = await asyncio.to_thread(download_draft_pdf, draft["fkey"])
    except VnptError as e:
        log.error("vnpt pdf failed tid=%s fkey=%s: %s", tid, draft.get("fkey"), e)
        return web.Response(text=f"Lỗi tải PDF từ VNPT: {e}", status=502)
    return web.Response(
        body=pdf, content_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="HD-nhap-{tid}.pdf"'})


def register_vnpt_invoice_routes(r) -> None:
    r.add_get("/api/order/{thread_id}/vnpt-invoice", vnpt_invoice_get_handler)
    r.add_post("/api/order/{thread_id}/vnpt-invoice", vnpt_invoice_save_handler)
    r.add_delete("/api/order/{thread_id}/vnpt-invoice", vnpt_invoice_delete_handler)
    r.add_get("/api/order/{thread_id}/vnpt-invoice/pdf", vnpt_invoice_pdf_handler)
