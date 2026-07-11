"""HTTP phiếu NHẬP HÀNG — /api/purchases (100% local, không KiotViet).

GET list phân trang (dashboard) / POST tạo (văn phòng, body {supplier_id, items,
note?}) / GET {id} / POST {id}/update sửa (văn phòng) / POST {id}/delete xoá mềm
(admin). Items dùng chung bảng SẢN PHẨM: mã resolve qua product_store (nhận cả mã
cũ) → gắn sp_id; hiển thị mã/tên bản hiện hành như đơn.
Nối: purchase_store, supplier_store, product_store, server_app.realtime, audit_log.
Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from purchase_store import (add_purchase, count_all_purchases, get_purchase,
                            get_purchase_full, list_all_purchases,
                            soft_delete_purchase, update_purchase_items)
from utils.db import get_connection

log = logging.getLogger("purchase_routes")


def _actor(request: web.Request) -> str:
    u = request.get("web_user")
    if isinstance(u, dict):
        return str(u.get("display_name") or u.get("username") or "web")
    return str(u or "web")


def _normalize_items(conn, items: list[dict]) -> list[dict]:
    """Gắn sp_id + chuẩn hoá mã về hiện hành (nhận cả mã cũ) — như phiếu trả/đơn.
    Mã không resolve được vẫn giữ nguyên (NCC có thể có hàng ngoài danh mục)."""
    from product_store import resolve_code
    out = []
    for it in items:
        it = dict(it)
        prod = resolve_code(conn, it.get("sp"))
        if prod:
            it["sp"] = prod["code"]
            it["sp_id"] = prod["id"]
        out.append(it)
    return out


def _items_display(conn, row: dict | None) -> dict | None:
    """Mã/tên item hiển thị = bản hiện hành (fallback snapshot)."""
    if row and row.get("items"):
        from order_store.display import resolve_invoice_display
        row = {**row, "items": resolve_invoice_display(row["items"], conn)}
    return row


def _parse_items(body: dict) -> tuple[list[dict], float] | None:
    """[{sp, sl, price}] → (items, tổng). Giá ≥ 0 (hàng tặng kèm giá 0 hợp lệ).
    None = không hợp lệ."""
    items = []
    total = 0.0
    for it in body.get("items") or []:
        sp = str(it.get("sp") or "").strip().upper()
        try:
            sl = float(it.get("sl") or 0)
            price = float(it.get("price") or 0)
        except (TypeError, ValueError):
            return None
        if not sp or sl <= 0 or price < 0:
            return None
        items.append({"sp": sp, "sl": sl, "price": price})
        total += sl * price
    return (items, total) if items else None


async def purchases_all_handler(request: web.Request):
    """GET /api/purchases?page= — dashboard nhập hàng (mọi NCC, 20/trang)."""
    try:
        page = max(1, int(request.query.get("page", "1")))
    except ValueError:
        page = 1
    limit = 20

    def _run():
        conn = get_connection()
        try:
            rows = [_items_display(conn, r) for r in list_all_purchases(conn, limit=limit, offset=(page - 1) * limit)]
            return rows, count_all_purchases(conn)
        finally:
            conn.close()
    rows, total = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "purchases": rows, "page": page,
                              "total": total, "total_pages": max(1, (total + limit - 1) // limit)})


async def purchase_detail_handler(request: web.Request):
    """GET /api/purchases/{id} — chi tiết 1 phiếu nhập (kèm tên NCC)."""
    try:
        pid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    def _get():
        conn = get_connection()
        try:
            return _items_display(conn, get_purchase_full(conn, pid))
        finally:
            conn.close()
    row = await asyncio.to_thread(_get)
    if not row:
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu nhập"}, status=404)
    return web.json_response({"ok": True, "purchase": row})


async def purchase_create_handler(request: web.Request):
    """POST /api/purchases (văn phòng) — body {supplier_id, items: [{sp, sl, price}], note?}."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được tạo phiếu nhập"}, status=403)
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        supplier_id = int(body.get("supplier_id") or 0)
    except (TypeError, ValueError):
        supplier_id = 0
    parsed = _parse_items(body)
    if not supplier_id or not parsed:
        return web.json_response(
            {"ok": False, "error": "Cần nhà cung cấp + danh sách hàng nhập (sp + sl>0 + giá≥0)"}, status=400)
    items, total = parsed
    note = str(body.get("note") or "").strip()
    actor = _actor(request)

    def _save():
        conn = get_connection()
        try:
            from supplier_store import get_supplier
            sup = get_supplier(conn, supplier_id)
            if not sup or sup.get("deleted_at"):
                return None
            return add_purchase(conn, supplier_id, _normalize_items(conn, items), total, note=note, by=actor)
        finally:
            conn.close()
    row = await asyncio.to_thread(_save)
    if not row:
        return web.json_response({"ok": False, "error": "Nhà cung cấp không tồn tại"}, status=400)

    from server_app.realtime import emit_purchase_changed, emit_supplier_changed
    emit_purchase_changed(row["id"])
    emit_supplier_changed(supplier_id)   # thống kê NCC (số phiếu/tổng tiền) đổi
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.purchase_created", async_log_event(
        "purchase.created", scope="purchase", thread_id=row["id"],
        actor_type="web_user" if request.get("web_user") else "http_client",
        actor_id=actor, source="purchase.created",
        payload={"supplier_id": supplier_id, "total": total}))
    return web.json_response({"ok": True, "purchase": row})


async def purchase_update_handler(request: web.Request):
    """POST /api/purchases/{id}/update (văn phòng) — sửa hàng nhập/ghi chú/NCC."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được sửa phiếu nhập"}, status=403)
    try:
        pid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    parsed = _parse_items(body)
    if not parsed:
        return web.json_response({"ok": False, "error": "Danh sách hàng nhập không hợp lệ"}, status=400)
    items, total = parsed
    note = str(body.get("note") or "").strip()
    new_supplier = body.get("supplier_id")
    row = await asyncio.to_thread(lambda: get_purchase(get_connection(), pid))
    if not row or row.get("deleted_at"):
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu nhập"}, status=404)

    def _upd():
        conn = get_connection()
        try:
            sid = None
            if new_supplier is not None:
                from supplier_store import get_supplier
                sup = get_supplier(conn, int(new_supplier))
                if not sup or sup.get("deleted_at"):
                    return False
                sid = int(new_supplier)
            update_purchase_items(conn, pid, _normalize_items(conn, items), total, note, supplier_id=sid)
            return True
        finally:
            conn.close()
    ok = await asyncio.to_thread(_upd)
    if not ok:
        return web.json_response({"ok": False, "error": "Nhà cung cấp không tồn tại"}, status=400)
    from server_app.realtime import emit_purchase_changed, emit_supplier_changed
    emit_purchase_changed(pid)
    emit_supplier_changed(int(row["supplier_id"]))
    if new_supplier is not None and int(new_supplier) != int(row["supplier_id"]):
        emit_supplier_changed(int(new_supplier))
    return web.json_response({"ok": True})


async def purchase_delete_handler(request: web.Request):
    """POST /api/purchases/{id}/delete (CHỈ admin) — xoá mềm phiếu nhập."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá phiếu nhập"}, status=403)
    try:
        pid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    row = await asyncio.to_thread(lambda: get_purchase(get_connection(), pid))
    if not row or row.get("deleted_at"):
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu nhập"}, status=404)
    actor = _actor(request)
    await asyncio.to_thread(lambda: soft_delete_purchase(get_connection(), pid, by=actor))
    from server_app.realtime import emit_purchase_changed, emit_supplier_changed
    emit_purchase_changed(pid)
    emit_supplier_changed(int(row["supplier_id"]))
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.purchase_deleted", async_log_event(
        "purchase.deleted", scope="purchase", thread_id=pid,
        actor_type="web_user", actor_id=actor, source="purchase.deleted",
        payload={"supplier_id": row["supplier_id"], "total": row.get("total")}))
    return web.json_response({"ok": True})
