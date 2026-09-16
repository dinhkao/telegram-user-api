"""API hoá đơn NHÁP VNPT cho webapp — GET/POST/DELETE /api/order/{tid}/vnpt-invoice.

Độc lập hoàn toàn với HĐ KiotViet (Duy chốt 2026-08-26). POST = tạo HOẶC sửa,
POST .../reset = tạo lại Y HỆT nội dung đang có (fkey mới) — cả hai đi qua
server_app/vnpt_invoice_push.push_draft: import nháp MỚI lên VNPT trước rồi mới
xoá nháp cũ, để không bao giờ mất nháp nếu import lỗi (updateInvoice bị VNPT
khoá trên TT78). Ghi blob đơn `$.vnpt_invoice` + cache khách `$.vnpt_profile`
(order_store/customers). Quyền: xem/tạo/sửa/reset = văn phòng, xoá = admin.
Logic thuần ở server_app/vnpt_invoice_domain.py; SOAP ở integrations/
vnpt_invoice/; PDF/PNG bản thể hiện ở server_app/vnpt_invoice_view_routes.py.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

from aiohttp import web

from order_db import _get_connection, _save_order, get_customer_by_key, get_order_by_thread_id, transaction
from order_store.customers import update_customer

from integrations.vnpt_invoice import delete_draft
from integrations.vnpt_invoice import core as vnpt_core
from integrations.vnpt_invoice.core import VnptError
from server_app.vnpt_invoice_domain import build_prefill, normalize_body, updated_profile
from server_app.vnpt_invoice_push import lock as _lock
from server_app.vnpt_invoice_push import push_draft

log = logging.getLogger("server")

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


# Throttle tra trạng thái phát hành: mỗi fkey hỏi VNPT tối đa 1 lần/30s
_status_checked: dict[str, float] = {}


async def _refresh_vnpt_status(conn, tid: int, draft: dict) -> dict:
    """Hỏi VNPT xem nháp đã PHÁT HÀNH chưa (kế toán phát hành trên portal, ngoài
    app) → vá blob nếu trạng thái đổi + realtime. Lỗi mạng/VNPT thì giữ nguyên
    trạng thái cũ, không được làm hỏng trang. Trả draft mới nhất."""
    fkey = draft.get("fkey")
    if not (draft.get("synced") and fkey):
        return draft
    now = time.time()
    if now - _status_checked.get(fkey, 0) < 30:
        return draft
    from integrations.vnpt_invoice import get_invoice_status
    try:
        st = await asyncio.to_thread(get_invoice_status, fkey)
    except Exception as e:  # noqa: BLE001 — kể cả VnptError: chỉ log, giữ trạng thái cũ
        log.warning("vnpt status check lỗi tid=%s fkey=%s: %s", tid, fkey, e)
        return draft
    if len(_status_checked) > 512:
        _status_checked.clear()
    _status_checked[fkey] = now
    same = (bool(draft.get("published")) == st["published"]
            and int(draft.get("invoice_no") or 0) == st["no"]
            and bool(draft.get("missing_on_vnpt")) == (not st["exists"]))
    if same:
        return draft
    with transaction(conn):
        fresh = get_order_by_thread_id(conn, tid)
        d2 = (fresh or {}).get("vnpt_invoice")
        if not d2 or d2.get("fkey") != fkey:      # nháp vừa bị thay/xoá song song — bỏ
            return d2 or draft
        d2["published"] = st["published"]
        d2["invoice_no"] = st["no"]
        d2["mtc"] = st.get("mtc") or ""
        d2["missing_on_vnpt"] = not st["exists"]
        d2["status_checked_at"] = datetime.now(UTC).isoformat()
        _save_order(conn, tid, fresh)
        draft = d2
    from server_app.realtime import emit_order_changed
    emit_order_changed(tid)
    if st["published"]:
        from audit_log import async_log_event
        from server_app.tasks import spawn_tracked
        spawn_tracked("audit.vnpt_published", async_log_event(
            "order.vnpt_published_detected", actor_type="system", actor_id="vnpt",
            thread_id=tid, payload={"fkey": fkey, "no": st["no"]}))
    return draft


async def vnpt_invoice_status_handler(request: web.Request):
    """GET .../vnpt-invoice/status — webapp gọi NỀN mỗi lần mở trang đơn để cập
    nhật 'đã phát hành chưa'. Trạng thái đổi → blob được vá + emit order_changed
    (trang tự reload). Throttle 30s/fkey."""
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
    draft = order.get("vnpt_invoice")
    if not draft:
        return web.json_response({"ok": True, "draft": None})
    draft = await _refresh_vnpt_status(conn, tid, draft)
    return web.json_response({"ok": True, "published": bool(draft.get("published")),
                              "invoice_no": int(draft.get("invoice_no") or 0),
                              "missing_on_vnpt": bool(draft.get("missing_on_vnpt"))})


async def vnpt_invoice_get_handler(request: web.Request):
    """Nháp hiện có (blob, đã làm tươi trạng thái phát hành) + prefill
    (cache khách ⊕ dòng hàng đơn ⊕ danh mục SP)."""
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
    draft = order.get("vnpt_invoice")
    if draft:
        draft = await _refresh_vnpt_status(conn, tid, draft)
    return web.json_response({
        "ok": True,
        "configured": vnpt_core.configured(),
        "pattern": vnpt_core.VNPT_INV_PATTERN,
        "serial": vnpt_core.VNPT_INV_SERIAL,
        "draft": draft,
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
    actor = str(request.get("web_user") or body.get("user_id") or "?")
    async with _lock(tid):
        old = (get_order_by_thread_id(conn, tid) or {}).get("vnpt_invoice") or {}
        if old.get("published"):
            return _err("Hoá đơn đã PHÁT HÀNH trên VNPT — không sửa nháp được nữa")
        try:
            draft, warn, fresh = await push_draft(
                conn, tid, buyer=buyer, lines=lines, vat_rate=vat_rate, actor=actor, old=old)
        except ValueError as e:
            return _err(str(e))
        except VnptError as e:
            return _err(f"VNPT từ chối: {e}", 502)
        except LookupError as e:
            return _err(str(e), 404)
        # Cache theo khách: lần sau tạo HĐ cho khách này là tự điền sẵn
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
        payload={"fkey": draft["fkey"], "amount": draft["amount"], "vat_rate": vat_rate,
                 "line_count": len(lines), "created": not old}))
    emit_order_changed(tid)
    return web.json_response({"ok": True, "fkey": draft["fkey"],
                              "amount": draft["amount"], "warn": warn})


async def vnpt_invoice_reset_handler(request: web.Request):
    """POST .../vnpt-invoice/reset — HUỶ nháp hiện tại rồi TẠO LẠI Y HỆT (fkey mới).

    Dùng khi bản nháp trên VNPT hỏng/kẹt, bị xoá tay trên portal
    (missing_on_vnpt) hoặc bản thể hiện hiện sai — nội dung giữ NGUYÊN 100%
    (buyer/dòng hàng/thuế lấy thẳng từ blob), không phải gõ lại gì.
    Vẫn theo thứ tự import-trước-xoá-sau của push_draft: lỗi giữa chừng thì nháp
    cũ còn nguyên, hơn là xoá xong mới hỏng và mất trắng."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return _err("Chỉ văn phòng mới được reset HĐ điện tử nháp", 403)
    tid = _tid(request)
    if tid is None:
        return _err("thread_id không hợp lệ")
    conn = _get_connection()
    actor = str(request.get("web_user") or "?")
    async with _lock(tid):
        order = get_order_by_thread_id(conn, tid)
        if not order:
            return _err("Không tìm thấy đơn", 404)
        old = order.get("vnpt_invoice")
        if not old:
            return _err("Đơn không có HĐ điện tử nháp để reset")
        if old.get("published"):
            return _err("Hoá đơn đã PHÁT HÀNH trên VNPT — không reset được; xử lý (huỷ/thay thế) trên trang VNPT")
        # Chuẩn hoá lại từ chính nội dung đang lưu (CK theo % tính lại đúng như
        # lúc lưu) — đi qua normalize_body để không đẩy blob cũ/lỗi thời lên VNPT
        try:
            buyer, lines, vat_rate = normalize_body(
                {"buyer": old.get("buyer") or {}, "lines": old.get("lines") or [],
                 "vat_rate": old.get("vat_rate")})
        except ValueError as e:
            return _err(f"Nháp đang lưu không hợp lệ ({e}) — mở trang sửa nháp để chỉnh lại")
        try:
            draft, warn, _fresh = await push_draft(
                conn, tid, buyer=buyer, lines=lines, vat_rate=vat_rate, actor=actor, old=old)
        except ValueError as e:
            return _err(str(e))
        except VnptError as e:
            return _err(f"VNPT từ chối: {e}", 502)
        except LookupError as e:
            return _err(str(e), 404)
    from audit_log import async_log_event
    from server_app.realtime import emit_order_changed
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.vnpt_draft_reset", async_log_event(
        "order.vnpt_draft_reset", actor_type="web", actor_id=actor, thread_id=tid,
        payload={"fkey": draft["fkey"], "old_fkey": old.get("fkey"),
                 "amount": draft["amount"]}))
    emit_order_changed(tid)
    return web.json_response({"ok": True, "fkey": draft["fkey"],
                              "amount": draft["amount"], "warn": warn})


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
        if draft.get("published"):
            return _err("Hoá đơn đã PHÁT HÀNH trên VNPT — không xoá được; xử lý (huỷ/thay thế) trên trang VNPT")
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


def register_vnpt_invoice_routes(r) -> None:
    r.add_get("/api/order/{thread_id}/vnpt-invoice", vnpt_invoice_get_handler)
    r.add_post("/api/order/{thread_id}/vnpt-invoice", vnpt_invoice_save_handler)
    r.add_delete("/api/order/{thread_id}/vnpt-invoice", vnpt_invoice_delete_handler)
    r.add_post("/api/order/{thread_id}/vnpt-invoice/reset", vnpt_invoice_reset_handler)
    r.add_get("/api/order/{thread_id}/vnpt-invoice/status", vnpt_invoice_status_handler)
    from server_app.vnpt_invoice_view_routes import register_vnpt_invoice_view_routes
    register_vnpt_invoice_view_routes(r)
