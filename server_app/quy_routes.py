"""HTTP handlers cho SỔ QUỸ (webapp) — /api/quy*.

Layer mỏng trên quy_store (+ domain). Tạo/xoá phiếu → phát realtime quy_changed
(server_app/realtime) + ghi audit. Payment tiền mặt của đơn KHÔNG đi qua đây — nó
tạo phiếu thu 'order' trực tiếp trong order_commands_v3._process_payment_core.
Đăng ký ở app_factory.

Kết nối: quy_store, quy_store.domain, server_app.realtime, audit_log.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from quy_store import (
    create_quy_table,
    migrate_quy_table,
    create_receipt,
    get_receipt,
    list_receipts,
    count_receipts,
    summary,
    delete_receipt,
)
from quy_store.domain import normalize_type, parse_amount
from utils.db import get_connection

log = logging.getLogger("server")


def _conn():
    conn = get_connection()
    create_quy_table(conn)
    migrate_quy_table(conn)
    return conn


def _actor(request) -> str:
    return request.get("web_user") or request.remote or ""


def _emit():
    from server_app.realtime import emit_quy_changed
    emit_quy_changed()


# ─── reads ───────────────────────────────────────────────────────────────────
async def quy_list_handler(request: web.Request):
    try:
        page = max(1, int(request.query.get("page", "1")))
    except (ValueError, TypeError):
        page = 1
    try:
        limit = max(1, min(100, int(request.query.get("limit", "20"))))
    except (ValueError, TypeError):
        limit = 20
    type_filter = request.query.get("type") or None
    if type_filter not in ("thu", "chi"):
        type_filter = None
    q = (request.query.get("q") or "").strip() or None
    offset = (page - 1) * limit

    def _run():
        conn = _conn()
        try:
            total = count_receipts(conn, type_filter=type_filter, q=q)
            rows = list_receipts(conn, limit=limit, offset=offset, type_filter=type_filter, q=q)
            summ = summary(conn)
        finally:
            conn.close()
        return rows, total, summ

    rows, total, summ = await asyncio.to_thread(_run)
    return web.json_response({
        "ok": True, "receipts": rows, "total": total, "page": page, "limit": limit,
        "total_pages": max(1, (total + limit - 1) // limit), "summary": summ,
    })


async def quy_detail_handler(request: web.Request):
    try:
        rid = int(request.match_info.get("id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            return get_receipt(conn, rid)
        finally:
            conn.close()

    r = await asyncio.to_thread(_run)
    if not r:
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu"}, status=404)
    return web.json_response({"ok": True, "receipt": r})


# ─── writes ──────────────────────────────────────────────────────────────────
async def quy_create_handler(request: web.Request):
    """Tạo phiếu thu/chi tay. Body {type:'thu'|'chi', amount, note}."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    rtype = normalize_type(body.get("type"))
    if not rtype:
        return web.json_response({"ok": False, "error": "Loại phiếu phải là 'thu' hoặc 'chi'"}, status=400)
    amount = parse_amount(body.get("amount"))
    if not amount:
        return web.json_response({"ok": False, "error": "Số tiền phải là số dương"}, status=400)
    note = str(body.get("note") or "").strip()
    actor = _actor(request)

    def _run():
        conn = _conn()
        try:
            return create_receipt(conn, type=rtype, amount=amount, note=note,
                                  source="manual", created_by=actor)
        finally:
            conn.close()

    receipt = await asyncio.to_thread(_run)
    _emit()
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.quy_created", async_log_event(
        "quy.created", scope="quy", thread_id=receipt["id"],
        actor_type="web_user" if request.get("web_user") else "http_client",
        actor_id=actor, source="quy.created",
        payload={"type": rtype, "amount": amount, "note": note}))
    return web.json_response({"ok": True, "receipt": receipt})


async def quy_delete_handler(request: web.Request):
    try:
        rid = int(request.match_info.get("id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            r = get_receipt(conn, rid)
            if not r:
                return None, False
            if r.get("source") == "order":
                return r, False  # phiếu gắn đơn — xoá qua xoá thanh toán, không xoá tay
            return r, delete_receipt(conn, rid)
        finally:
            conn.close()

    r, ok = await asyncio.to_thread(_run)
    if r is None:
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu"}, status=404)
    if not ok:
        return web.json_response({"ok": False, "error": "Phiếu gắn đơn hàng — xoá bằng cách xoá thanh toán trong đơn"}, status=400)
    _emit()
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.quy_deleted", async_log_event(
        "quy.deleted", scope="quy", thread_id=rid,
        actor_type="web_user" if request.get("web_user") else "http_client",
        actor_id=_actor(request), source="quy.deleted",
        payload={"type": r.get("type"), "amount": r.get("amount")}))
    return web.json_response({"ok": True, "id": rid})
