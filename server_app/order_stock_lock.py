"""Chốt xuất kho cho đơn — POST /api/order/{thread_id}/stock-confirm.

Chốt = ghi {at, by} vào $.stock_confirmed của blob đơn (orders, app.db). Điều kiện
chốt: mọi mã SP trong hoá đơn đã xuất ĐỦ số. Sau chốt, allocate/release bị KHOÁ
với MỌI NGƯỜI (inventory_routes gọi stock_locked_error trước khi ghi); admin muốn
sửa phải HUỶ CHỐT trước (huỷ chốt = admin-only). Nối: order_store.serialization, inventory_store, utils.db,
server_app.realtime, server_app.order_api_common (is_admin_request), audit_log.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

from aiohttp import web

from utils.db import get_connection

_VN_TZ = timezone(timedelta(hours=7))


def _get_confirmed(conn, thread_id: int) -> dict | None:
    """Trạng thái chốt xuất kho của đơn ({at, by}) hoặc None."""
    from order_store.serialization import get_order_by_thread_id
    order = get_order_by_thread_id(conn, thread_id) or {}
    v = order.get("stock_confirmed")
    return v if isinstance(v, dict) and v else None


async def stock_locked_error(request: web.Request, thread_id: int) -> web.Response | None:
    """Đơn đã chốt xuất kho → chặn allocate/release với MỌI NGƯỜI (403) — admin
    muốn sửa phải HUỶ CHỐT trước (nút Huỷ chốt, admin-only). None = được ghi."""
    def _read():
        conn = get_connection()
        try:
            return _get_confirmed(conn, thread_id)
        finally:
            conn.close()
    confirmed = await asyncio.to_thread(_read)
    if not confirmed:
        return None
    return web.json_response(
        {"ok": False, "error": "Đã chốt xuất kho — admin bấm Huỷ chốt mới sửa được", "locked": True},
        status=403,
    )


async def order_stock_confirm_handler(request: web.Request):
    """Body {confirm: true} = chốt (cần xuất ĐỦ mọi mã SP); {confirm: false} = huỷ
    chốt (CHỈ admin). Trả {ok, stock_confirmed}."""
    try:
        thread_id = int(request.match_info.get("thread_id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    confirm = bool(body.get("confirm", True))

    actor = request.get("web_user") or ""
    if isinstance(actor, dict):
        actor = str(actor.get("display_name") or actor.get("username") or "web")
    actor = str(actor or body.get("user") or "web")

    if not confirm:   # huỷ chốt — chỉ admin
        from server_app.order_api_common import is_admin_request
        if not await is_admin_request(request):
            return web.json_response({"ok": False, "error": "Chỉ admin huỷ chốt được"}, status=403)

    # Các thùng đang xuất cho đơn này → emit box_changed để ô thùng đổi màu (NÂU↔XANH)
    box_ids: list[int] = []

    def _run():
        conn = get_connection()
        try:
            from order_store.serialization import get_order_by_thread_id, _update_order_json_field
            order = get_order_by_thread_id(conn, thread_id)
            if not order:
                return "notfound", None
            from inventory_store import list_order_allocations
            allocs = list_order_allocations(conn, thread_id)
            box_ids[:] = [a["box_id"] for a in allocs if a.get("box_id") is not None]
            if not confirm:
                _update_order_json_field(conn, thread_id, "$.stock_confirmed", None)
                conn.commit()
                return "ok", None
            if isinstance(order.get("stock_confirmed"), dict) and order["stock_confirmed"]:
                return "ok", order["stock_confirmed"]   # đã chốt rồi — idempotent
            # điều kiện: mọi mã SP trong hoá đơn đã xuất đủ
            needs: dict[str, float] = {}
            for it in order.get("invoice") or []:
                code = str(it.get("sp") or "").strip().upper()
                if code:
                    try:
                        needs[code] = needs.get(code, 0.0) + float(it.get("sl") or 0)
                    except (TypeError, ValueError):
                        pass
            if not needs:
                return "empty", None
            got: dict[str, float] = {}
            for a in allocs:
                got[a["product_code"]] = got.get(a["product_code"], 0.0) + (a.get("quantity") or 0)
            short = [c for c, need in needs.items() if got.get(c, 0.0) + 1e-6 < need]
            if short:
                return "short", short
            state = {"at": datetime.now(_VN_TZ).isoformat(timespec="seconds"), "by": actor}
            _update_order_json_field(conn, thread_id, "$.stock_confirmed", state)
            conn.commit()
            return "ok", state
        finally:
            conn.close()

    status, payload = await asyncio.to_thread(_run)
    if status == "notfound":
        return web.json_response({"ok": False, "error": "Không tìm thấy đơn"}, status=404)
    if status == "empty":
        return web.json_response({"ok": False, "error": "Đơn chưa có hoá đơn — không có gì để chốt"}, status=400)
    if status == "short":
        return web.json_response(
            {"ok": False, "error": f"Chưa xuất đủ: {', '.join(payload)} — xuất đủ mới chốt được"}, status=400)

    from server_app.realtime import emit_order_changed, emit_inventory_changed, emit_box_changed
    emit_order_changed(thread_id)
    emit_inventory_changed()          # trang Kho / SP tải lại → ô thùng đổi màu NÂU↔XANH
    for bid in box_ids:               # chi tiết từng thùng đang xuất cho đơn
        emit_box_changed(bid)
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.stock_confirm", async_log_event(
        "order.stock_confirmed" if confirm else "order.stock_unconfirmed",
        scope="order", thread_id=thread_id,
        actor_type="web_user" if request.get("web_user") else "http_client",
        actor_id=actor, source="order.stock_confirm",
        payload={"confirm": confirm}))
    return web.json_response({"ok": True, "stock_confirmed": payload})
