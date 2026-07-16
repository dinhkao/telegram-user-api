"""API PHIẾU ĐIỀU CHỈNH tồn kho 1 thùng — /api/inventory/box/{id}/adjust + /api/adjustments*.

Điều chỉnh tay (nhập TỒN THỰC TẾ + lý do bắt buộc) = VĂN PHÒNG; gỡ phiếu = ADMIN
(hoàn nguyên, guard tồn âm). Store: inventory_store/adjustments.py (allocation
kind='adjustment', không sửa quantity gốc). Audit adjustment.created/deleted ghi
CẢ scope box LẪN place (inventory_audit.log_box_adjustment, snapshot sau biến
động) → timeline thùng/SP/vị trí thấy điều chỉnh. Realtime inventory/box_changed.
Đăng ký ở app_factory.
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


def _audit(action: str, snap: dict | None, adj: dict, actor: str, request: web.Request) -> None:
    """Ghi event điều chỉnh cho CẢ lịch sử thùng lẫn vị trí (timeline đọc)."""
    if not snap:
        return
    from server_app.inventory_audit import log_box_adjustment
    log_box_adjustment(action, snap, adjustment_id=adj.get("id") or adj.get("adjustment_id"),
                       delta=adj.get("delta"), reason=adj.get("reason"), actor=actor,
                       actor_type="web_user" if request.get("web_user") else "http_client")


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
        from server_app.inventory_audit import box_snapshot
        conn = get_connection()
        try:
            adj, err = create_adjustment(conn, box_id, new_remaining=body.get("new_remaining"),
                                         reason=str(body.get("reason") or ""), by=actor)
            snap = box_snapshot(conn, box_id) if adj else None   # SAU biến động (đã commit)
            return adj, err, snap
        finally:
            conn.close()

    adj, err, snap = await asyncio.to_thread(_run)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)
    from server_app.realtime import emit_box_changed, emit_inventory_changed
    emit_inventory_changed()
    emit_box_changed(box_id)
    _audit("adjustment.created", snap, adj, actor, request)
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
        from server_app.inventory_audit import box_snapshot
        conn = get_connection()
        try:
            adj, err = delete_adjustment(conn, adj_id, by=actor)
            snap = box_snapshot(conn, int(adj["box_id"])) if adj else None   # SAU hoàn nguyên
            return adj, err, snap
        finally:
            conn.close()

    adj, err, snap = await asyncio.to_thread(_run)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)
    from server_app.realtime import emit_box_changed, emit_inventory_changed
    emit_inventory_changed()
    emit_box_changed(adj["box_id"])
    _audit("adjustment.deleted", snap, {**adj, "id": adj_id}, actor, request)
    return web.json_response({"ok": True})


def register(r: web.UrlDispatcher) -> None:
    r.add_post("/api/inventory/box/{box_id}/adjust", box_adjust_handler)
    r.add_get("/api/adjustments", adjustments_list_handler)
    r.add_post("/api/adjustments/{id}/delete", adjustment_delete_handler)
