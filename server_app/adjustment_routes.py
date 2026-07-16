"""API PHIẾU ĐIỀU CHỈNH tồn kho 1 thùng — /api/inventory/box/{id}/adjust + /api/adjustments*.

Điều chỉnh tay (nhập TỒN THỰC TẾ + lý do bắt buộc) = VĂN PHÒNG; gỡ phiếu = ADMIN
(hoàn nguyên, guard tồn âm). Store: inventory_store/adjustments.py (allocation
kind='adjustment', không sửa quantity gốc). Audit adjustment.created/deleted
(scope='box') + realtime inventory/box_changed. Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from utils.db import get_connection


def _actor(request: web.Request) -> str:
    u = request.get("web_user")
    return str((u or {}).get("display_name") or (u or {}).get("username") or "web") if isinstance(u, dict) else str(u or "web")


def _int_match(request: web.Request, key: str) -> int | None:
    try:
        return int(request.match_info.get(key, ""))
    except (TypeError, ValueError):
        return None


def _audit(action: str, box_id: int, actor: str, request: web.Request, **payload) -> None:
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked(f"audit.{action}", async_log_event(
        action, scope="box", thread_id=box_id,
        actor_type="web_user" if request.get("web_user") else "http_client",
        actor_id=actor, source=action, payload=payload))


async def box_adjust_handler(request: web.Request):
    """POST /api/inventory/box/{box_id}/adjust (văn phòng) — body {new_remaining, reason}.
    Tạo phiếu điều chỉnh đưa tồn thùng về đúng số THỰC TẾ; delta tính trong transaction."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng được điều chỉnh tồn kho"}, status=403)
    box_id = _int_match(request, "box_id")
    if box_id is None:
        return web.json_response({"ok": False, "error": "box_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    actor = _actor(request)

    def _run():
        from inventory_store.adjustments import create_adjustment
        conn = get_connection()
        try:
            return create_adjustment(conn, box_id, new_remaining=body.get("new_remaining"),
                                     reason=str(body.get("reason") or ""), by=actor)
        finally:
            conn.close()

    adj, err = await asyncio.to_thread(_run)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)
    from server_app.realtime import emit_box_changed, emit_inventory_changed
    emit_inventory_changed()
    emit_box_changed(box_id)
    _audit("adjustment.created", box_id, actor, request,
           adjustment_id=adj["id"], box_id=box_id, box_code=adj.get("box_code"),
           product_code=adj.get("product_code"), delta=adj.get("delta"),
           new_remaining=adj.get("new_remaining"), reason=adj.get("reason"))
    return web.json_response({"ok": True, "adjustment": adj})


async def adjustments_list_handler(request: web.Request):
    """GET /api/adjustments?box_id=&stocktake_id= — phiếu điều chỉnh mới→cũ."""
    def _num(key):
        v = request.query.get(key)
        try:
            return int(v) if v else None
        except ValueError:
            return None
    box_id, stocktake_id = _num("box_id"), _num("stocktake_id")

    def _run():
        from inventory_store.adjustments import list_adjustments
        conn = get_connection()
        try:
            return list_adjustments(conn, box_id=box_id, stocktake_id=stocktake_id)
        finally:
            conn.close()

    rows = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "adjustments": rows})


async def adjustment_delete_handler(request: web.Request):
    """POST /api/adjustments/{id}/delete (ADMIN) — gỡ phiếu = hoàn nguyên điều chỉnh.
    Chặn nếu phần tồn đã tăng đã bị dùng (gỡ sẽ làm tồn âm)."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được gỡ phiếu điều chỉnh"}, status=403)
    adj_id = _int_match(request, "id")
    if adj_id is None:
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    actor = _actor(request)

    def _run():
        from inventory_store.adjustments import delete_adjustment
        conn = get_connection()
        try:
            return delete_adjustment(conn, adj_id, by=actor)
        finally:
            conn.close()

    adj, err = await asyncio.to_thread(_run)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)
    from server_app.realtime import emit_box_changed, emit_inventory_changed
    emit_inventory_changed()
    emit_box_changed(adj["box_id"])
    _audit("adjustment.deleted", int(adj["box_id"]), actor, request,
           adjustment_id=adj_id, box_id=int(adj["box_id"]), box_code=adj.get("box_code"),
           product_code=adj.get("product_code"), delta=adj.get("delta"), reason=adj.get("reason"))
    return web.json_response({"ok": True})


def register(r: web.UrlDispatcher) -> None:
    r.add_post("/api/inventory/box/{box_id}/adjust", box_adjust_handler)
    r.add_get("/api/adjustments", adjustments_list_handler)
    r.add_post("/api/adjustments/{id}/delete", adjustment_delete_handler)
