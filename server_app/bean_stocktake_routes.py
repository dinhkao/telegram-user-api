"""HTTP PHIẾU KIỂM KHO ĐẬU — /api/beans/stocktakes (100% local).

GET danh sách (lọc kho/trạng thái, phân trang) · POST tạo (mọi user đăng nhập —
chụp sổ MỌI loại đậu của kho) · GET {id} · POST {id}/count (ghi số đếm 1+ dòng, mọi
user) · POST {id}/resync (đồng bộ sổ theo tồn hiện tại, giữ số đếm) · POST
{id}/complete (CHỐT → sinh phiếu điều chỉnh, mọi user — cùng quyền với phiếu điều
chỉnh thường; thông báo như phiếu) · POST {id}/void (huỷ nháp, văn phòng).
Audit scope `bean_stocktake` (id phiếu kiểm); realtime `bean_changed`.
Nối: bean_store.stocktakes, server_app.bean_routes (audit/_conn), bean_notify.
Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

import bean_store
from bean_store import domain
from server_app.bean_routes import _actor, _body, _conn, _emit, _int, _office, audit

log = logging.getLogger("bean_stocktake_routes")

_PAGE = 30


def _lines(st: dict, only_counted: bool = True) -> list[dict]:
    """Dòng gọn cho audit: tên đậu, sổ, đếm, chênh lệch."""
    out = []
    for i in st.get("items") or []:
        if only_counted and i.get("counted_qty") is None:
            continue
        out.append({"bean": i["bean_name"], "expected": i["expected_qty"],
                    "counted": i["counted_qty"], "diff": i.get("diff")})
    return out


def _qint(request: web.Request, key: str):
    v = request.query.get(key)
    try:
        return int(v) if v else None
    except (TypeError, ValueError):
        return None


async def bean_stocktakes_handler(request: web.Request):
    """GET /api/beans/stocktakes?place_id=&status=&page= — nháp lên đầu, rồi mới → cũ."""
    status = (request.query.get("status") or "").strip() or None
    if status and status not in domain.STOCKTAKE_STATUSES:
        return web.json_response({"ok": False, "error": "Trạng thái không hợp lệ"}, status=400)
    place_id = _qint(request, "place_id")
    page = max(1, _qint(request, "page") or 1)

    def _run():
        conn = _conn()
        try:
            return bean_store.list_stocktakes(conn, place_id=place_id, status=status,
                                              limit=_PAGE, offset=(page - 1) * _PAGE)
        finally:
            conn.close()
    rows, total = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "stocktakes": rows, "page": page, "total": total,
                              "total_pages": max(1, -(-total // _PAGE))})


async def bean_stocktake_detail_handler(request: web.Request):
    """GET /api/beans/stocktakes/{id} — phiếu + dòng (sổ, đếm, chênh lệch, cờ stale)."""
    sid = _int(request)
    if sid is None:
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            return bean_store.get_stocktake(conn, sid)
        finally:
            conn.close()
    st = await asyncio.to_thread(_run)
    if not st:
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu kiểm"}, status=404)
    return web.json_response({"ok": True, "stocktake": st})


async def bean_stocktake_create_handler(request: web.Request):
    """POST /api/beans/stocktakes {place_id, note?} — mọi user; 1 nháp/kho."""
    body = await _body(request)
    actor = _actor(request)

    def _save():
        conn = _conn()
        try:
            return bean_store.create_stocktake(conn, body.get("place_id"),
                                               note=str(body.get("note") or ""), by=actor)
        finally:
            conn.close()
    st, err = await asyncio.to_thread(_save)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)
    _emit()
    audit("bean.stocktake_created", st["id"], request, {
        "stocktake_id": st["id"], "place_id": st["place_id"], "place_name": st["place_name"],
        "lines": len(st["items"])}, scope="bean_stocktake")
    return web.json_response({"ok": True, "stocktake": st})


def _mutate(fn_name: str, action: str, *, office: bool = False, emit_slip: bool = False):
    """Handler POST /api/beans/stocktakes/{id}/<op> dùng chung cho count/resync/complete/void."""
    async def handler(request: web.Request):
        if office and not await _office(request):
            return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được huỷ phiếu kiểm"},
                                     status=403)
        sid = _int(request)
        if sid is None:
            return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
        body = await _body(request)
        actor = _actor(request)

        def _run():
            conn = _conn()
            try:
                fn = getattr(bean_store, fn_name)
                if fn_name == "set_counts":
                    return fn(conn, sid, body.get("items"), by=actor)
                if fn_name == "complete_stocktake":
                    return fn(conn, sid, by=actor, note=str(body.get("note") or ""))
                return fn(conn, sid, by=actor)
            finally:
                conn.close()
        st, err = await asyncio.to_thread(_run)
        if err:
            status = 404 if "Không tìm thấy" in err else 400
            return web.json_response({"ok": False, "error": err}, status=status)
        _emit()
        payload = {"stocktake_id": sid, "place_id": st["place_id"], "place_name": st["place_name"],
                   "summary": st["summary"]}
        if fn_name == "set_counts":
            # Chỉ ghi các dòng vừa gửi (không phải cả phiếu) để lịch sử nói đúng "ai đếm gì".
            sent = {int(i.get("bean_id")) for i in (body.get("items") or []) if isinstance(i, dict)
                    and str(i.get("bean_id") or "").lstrip("-").isdigit()}
            payload["lines"] = [l for l, i in zip(_lines(st, False), st["items"]) if i["bean_id"] in sent]
        elif fn_name == "complete_stocktake":
            payload["lines"] = [l for l in _lines(st) if l["diff"]]
            payload["slip_id"] = st.get("slip_id")
            if emit_slip and st.get("slip_id"):
                _notify_slip(st["slip_id"], actor)
        audit(action, sid, request, payload, scope="bean_stocktake")
        return web.json_response({"ok": True, "stocktake": st})
    return handler


def _notify_slip(slip_id: int, actor: str) -> None:
    """Phiếu điều chỉnh sinh từ chốt kiểm kho → thông báo y như phiếu tạo tay."""
    def _run():
        conn = _conn()
        try:
            return bean_store.get_slip(conn, slip_id)
        finally:
            conn.close()

    async def _go():
        slip = await asyncio.to_thread(_run)
        if slip:
            from server_app.bean_notify import notify_bean_slip
            notify_bean_slip(slip, actor)
    from server_app.tasks import spawn_tracked
    spawn_tracked("bean.stocktake_notify", _go())


bean_stocktake_count_handler = _mutate("set_counts", "bean.stocktake_counted")
bean_stocktake_resync_handler = _mutate("resync_stocktake", "bean.stocktake_resynced")
bean_stocktake_complete_handler = _mutate("complete_stocktake", "bean.stocktake_completed",
                                          emit_slip=True)
bean_stocktake_void_handler = _mutate("void_stocktake", "bean.stocktake_voided", office=True)
