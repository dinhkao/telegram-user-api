"""HTTP phiếu TRẢ HÀNG — /api/customers/{key}/returns (+ xoá).

POST (văn phòng): tạo HĐ KiotViet GIÁ ÂM (sl dương × giá âm — public API không có
POST /returns, số lượng âm bị chặn) → ghi return_slips + cập nhật nợ khách +
resync nền vá debt_after. DELETE (admin): xoá HĐ KV + xoá mềm phiếu.
Nối: return_store, integrations.kiotviet, server_app.debt_sync, server_app.realtime,
audit_log. Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from return_store import add_return, get_return, list_returns, soft_delete_return
from utils.db import get_connection

log = logging.getLogger("return_routes")


def _actor(request: web.Request) -> str:
    u = request.get("web_user")
    if isinstance(u, dict):
        return str(u.get("display_name") or u.get("username") or "web")
    return str(u or "web")


def _parse_items(body: dict) -> tuple[list[dict], float] | None:
    """[{sp, sl, price}] (giá DƯƠNG) → (items chuẩn hoá, tổng). None = không hợp lệ."""
    items = []
    total = 0.0
    for it in body.get("items") or []:
        sp = str(it.get("sp") or "").strip().upper()
        try:
            sl = float(it.get("sl") or 0)
            price = float(it.get("price") or 0)
        except (TypeError, ValueError):
            return None
        if not sp or sl <= 0 or price <= 0:
            return None
        items.append({"sp": sp, "sl": sl, "price": price})
        total += sl * price
    return (items, total) if items and total > 0 else None


async def returns_list_handler(request: web.Request):
    key = request.match_info.get("key", "").strip()
    if not key:
        return web.json_response({"ok": False, "error": "thiếu key"}, status=400)
    rows = await asyncio.to_thread(lambda: list_returns(get_connection(), key))
    return web.json_response({"ok": True, "returns": rows})


async def returns_create_handler(request: web.Request):
    """Body {items: [{sp, sl, price}], note?, thread_id?} — giá DƯƠNG (tiền trả)."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được tạo phiếu trả hàng"}, status=403)
    key = request.match_info.get("key", "").strip()
    try:
        body = await request.json()
    except Exception:
        body = {}
    parsed = _parse_items(body)
    if not key or not parsed:
        return web.json_response({"ok": False, "error": "Danh sách hàng trả không hợp lệ (cần sp + sl>0 + giá>0)"}, status=400)
    items, total = parsed
    note = str(body.get("note") or "").strip()
    thread_id = body.get("thread_id")
    actor = _actor(request)

    def _kh_id():
        conn = get_connection()
        try:
            r = conn.execute(
                "SELECT json_extract(json,'$.kh_id') FROM customers WHERE firebase_key = ? AND deleted_at IS NULL",
                (key,)).fetchone()
            return r[0] if r else None
        finally:
            conn.close()
    kh_id = await asyncio.to_thread(_kh_id)
    if not kh_id:
        return web.json_response({"ok": False, "error": "Khách chưa liên kết KiotViet"}, status=400)

    # HĐ KV GIÁ ÂM: sl giữ dương, price đổi dấu → tổng HĐ âm, KV trừ thẳng nợ
    from integrations.kiotviet.customers import get_customer_debt_kv
    from integrations.kiotviet.invoices import create_kiotviet_invoice
    kv_items = [{"sp": it["sp"], "sl": int(it["sl"]), "price": -int(it["price"])} for it in items]
    try:
        debt_before = (await asyncio.to_thread(get_customer_debt_kv, kh_id)).get("debt")
    except Exception:
        debt_before = None
    try:
        inv = await asyncio.to_thread(
            create_kiotviet_invoice, customer_id=int(kh_id), invoice_items=kv_items)
    except Exception as e:
        log.error("create return invoice failed key=%s: %s", key, e)
        return web.json_response({"ok": False, "error": f"Lỗi tạo HĐ trả hàng KiotViet: {e}"}, status=502)

    debt_after = (float(debt_before) - total) if debt_before is not None else None

    def _save():
        conn = get_connection()
        try:
            row = add_return(conn, key, items, total, note=note, thread_id=thread_id,
                             kv_invoice_id=inv.get("id"), kv_invoice_code=inv.get("code"),
                             debt_before=debt_before, debt_after=debt_after, by=actor)
            if debt_after is not None:
                from order_db import update_customer_debt
                update_customer_debt(conn, key, debt_after)
            return row
        finally:
            conn.close()
    row = await asyncio.to_thread(_save)

    # resync nền: lấy nợ KV thật (+6s/+30s) vá debt_after + customers.debt
    from server_app.debt_sync import schedule_debt_resync
    schedule_debt_resync(key, return_id=row["id"])
    from server_app.realtime import emit_customer_changed
    emit_customer_changed(key)
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.return_created", async_log_event(
        "return.created", scope="customer", thread_id=int(thread_id or 0),
        actor_type="web_user" if request.get("web_user") else "http_client",
        actor_id=actor, source="return.created",
        payload={"customer_key": key, "return_id": row["id"], "total": total,
                 "kv_code": inv.get("code")}))
    return web.json_response({"ok": True, "return": row})


async def returns_delete_handler(request: web.Request):
    """Xoá phiếu trả (CHỈ admin): xoá HĐ KV âm + xoá mềm row + resync nợ."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá phiếu trả hàng"}, status=403)
    try:
        rid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    row = await asyncio.to_thread(lambda: get_return(get_connection(), rid))
    if not row or row.get("deleted_at"):
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu trả"}, status=404)
    if row.get("kv_invoice_id"):
        from integrations.kiotviet.invoices import delete_invoice_kv
        try:
            await asyncio.to_thread(delete_invoice_kv, int(row["kv_invoice_id"]))
        except Exception as e:
            log.error("delete return invoice failed id=%s: %s", rid, e)
            return web.json_response({"ok": False, "error": f"Lỗi xoá HĐ KiotViet: {e}"}, status=502)
    actor = _actor(request)
    await asyncio.to_thread(lambda: soft_delete_return(get_connection(), rid, by=actor))
    from server_app.debt_sync import schedule_debt_resync
    schedule_debt_resync(str(row["customer_key"]))
    from server_app.realtime import emit_customer_changed
    emit_customer_changed(str(row["customer_key"]))
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.return_deleted", async_log_event(
        "return.deleted", scope="customer", thread_id=int(row.get("thread_id") or 0),
        actor_type="web_user", actor_id=actor, source="return.deleted",
        payload={"customer_key": row["customer_key"], "return_id": rid, "kv_code": row.get("kv_invoice_code")}))
    return web.json_response({"ok": True})
