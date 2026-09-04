"""HTTP PHIẾU KHO ĐẬU — nhập / xuất / điều chỉnh: /api/beans/slips (100% local).

GET danh sách (lọc theo loại/kho/đậu, phân trang) · GET {id} chi tiết · POST tạo
(mọi user đăng nhập, đẩy THÔNG BÁO qua server_app.bean_notify) · POST {id}/delete
(admin, xoá mềm — tồn tự hoàn).
Nối: bean_store.slips, server_app.bean_routes (_conn/audit dùng chung),
server_app.bean_notify, server_app.realtime. Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

import bean_store
from bean_store import domain
from server_app.bean_routes import audit
from utils.db import get_connection

log = logging.getLogger("bean_slip_routes")

_PAGE = 30


def _conn():
    conn = get_connection()
    bean_store.ensure_tables(conn)
    return conn


def _actor(request: web.Request) -> str:
    u = request.get("web_user")
    if isinstance(u, dict):
        return str(u.get("display_name") or u.get("username") or "web")
    return str(u or "web")


def _emit() -> None:
    from server_app.realtime import emit_bean_changed
    emit_bean_changed()


def _place_label(slip: dict) -> str:
    """Tên kho cho audit/lịch sử — phiếu chuyển ghi cả 2 đầu 'Kho A → Kho B'."""
    src = str(slip.get("place_name") or "")
    dst = str(slip.get("dest_place_name") or "")
    return f"{src} → {dst}" if slip.get("kind") == "chuyen" and dst else src


def _qint(request: web.Request, key: str):
    v = request.query.get(key)
    try:
        return int(v) if v else None
    except (TypeError, ValueError):
        return None


async def bean_slips_handler(request: web.Request):
    """GET /api/beans/slips?kind=&place_id=&bean_id=&page= — phiếu mới → cũ."""
    kind = (request.query.get("kind") or "").strip() or None
    if kind and kind not in domain.KINDS:
        return web.json_response({"ok": False, "error": "Loại phiếu không hợp lệ"}, status=400)
    place_id, bean_id = _qint(request, "place_id"), _qint(request, "bean_id")
    page = max(1, _qint(request, "page") or 1)

    def _run():
        conn = _conn()
        try:
            return bean_store.list_slips(conn, kind=kind, place_id=place_id, bean_id=bean_id,
                                         limit=_PAGE, offset=(page - 1) * _PAGE)
        finally:
            conn.close()
    slips, total = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "slips": slips, "page": page, "total": total,
                              "total_pages": max(1, -(-total // _PAGE))})


async def bean_slip_detail_handler(request: web.Request):
    """GET /api/beans/slips/{id} — 1 phiếu + các dòng đậu."""
    try:
        sid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            return bean_store.get_slip(conn, sid)
        finally:
            conn.close()
    slip = await asyncio.to_thread(_run)
    if not slip:
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu"}, status=404)
    return web.json_response({"ok": True, "slip": slip})


async def bean_slip_create_handler(request: web.Request):
    """POST /api/beans/slips — MỌI user đăng nhập tạo phiếu.

    body: {kind: nhap|xuat|dieu_chinh|chuyen, place_id, items: [{bean_id, quantity, note}],
           partner, note, ymd, dest_place_id?}. Điều chỉnh: quantity = SỐ ĐẾM THỰC TẾ
    (không phải chênh lệch). Chuyển kho: place_id = kho NGUỒN, dest_place_id = kho ĐÍCH.
    """
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    if not isinstance(body, dict):
        body = {}
    actor = _actor(request)

    def _save():
        conn = _conn()
        try:
            return bean_store.create_slip(
                conn, body.get("kind"), body.get("place_id"), body.get("items"),
                dest_place_id=body.get("dest_place_id"),
                partner=str(body.get("partner") or ""), note=str(body.get("note") or ""),
                ymd=str(body.get("ymd") or "") or None, by=actor)
        finally:
            conn.close()
    slip, err = await asyncio.to_thread(_save)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)

    _emit()
    from server_app.bean_notify import notify_bean_slip
    notify_bean_slip(slip, actor)   # chuông trong app + push FCM
    audit(f"bean.slip_{slip['kind']}", slip["id"], request, {
        "slip_id": slip["id"], "kind": slip["kind"], "place_name": _place_label(slip),
        "lines": [{"bean": i["bean_name"], "qty": i["quantity"], "delta": i["delta"]}
                  for i in slip["items"]],
    }, scope="bean_slip")
    return web.json_response({"ok": True, "slip": slip})


async def bean_slip_delete_handler(request: web.Request):
    """POST /api/beans/slips/{id}/delete — CHỈ admin. Xoá mềm, tồn tự hoàn lại."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá phiếu"}, status=403)
    try:
        sid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    actor = _actor(request)

    def _del():
        conn = _conn()
        try:
            return bean_store.soft_delete_slip(conn, sid, by=actor)
        finally:
            conn.close()
    slip, err = await asyncio.to_thread(_del)
    if err:
        status = 404 if "Không tìm thấy" in err else 400
        return web.json_response({"ok": False, "error": err}, status=status)

    _emit()
    audit("bean.slip_deleted", sid, request, {
        "slip_id": sid, "kind": slip["kind"], "place_name": _place_label(slip),
        "lines": [{"bean": i["bean_name"], "qty": i["quantity"]} for i in slip["items"]],
    }, scope="bean_slip")
    return web.json_response({"ok": True})
