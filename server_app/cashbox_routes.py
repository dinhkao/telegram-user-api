"""API hệ KÉT TIỀN "ai đang giữ tiền" — /api/cashbox*. Đăng ký ở app_factory.

GET tổng quan + timeline (derive từ blob đơn, cashbox_store.service; staff chỉ
thấy két mình, văn phòng thấy hết); POST chuyển tiền tay giữa két (văn phòng,
chặn rút quá số dư, serialize bằng _transfer_lock) + xoá (admin). ⚠ Lọc
staff-chỉ-thấy-két-mình là lọc MỀM: request không token khi WEB_AUTH_ENABLED=false
thấy hết — cùng posture Tailscale với /api/quy và toàn bộ /api/* (REVIEW_REPORT.md).
Kết nối: cashbox_store, utils/db.py, server_app/realtime (emit_cashbox_changed),
server_app/order_api_common (gates).
"""
from __future__ import annotations

import asyncio
import time

from aiohttp import web

import cashbox_store
from cashbox_store.identity import BOX_NAMES
from cashbox_store.service import box_exists, cashbox_balance, cashbox_summary, cashbox_timeline
from server_app.order_api_common import is_admin_request, is_office_request
from utils.db import get_connection

# Chuyển tiền là check-then-insert → serialize để 2 lệnh đồng thời không cùng
# vượt qua bước kiểm số dư rồi rút âm két (server 1 process nên lock này đủ).
_transfer_lock = asyncio.Lock()


async def _viewer(request: web.Request) -> str | None:
    """None = thấy hết (văn phòng / auth tắt); username = staff chỉ thấy két mình."""
    user = request.get("web_user")
    if not user or await is_office_request(request):
        return None
    return str(user)


async def cashbox_summary_handler(request: web.Request):
    """GET /api/cashbox — tổng quan mọi két (số dư, đang giữ, quá hạn)."""
    viewer = await _viewer(request)
    data = await asyncio.to_thread(cashbox_summary, time.time(), viewer)
    return web.json_response(data)


async def cashbox_timeline_handler(request: web.Request):
    """GET /api/cashbox/{key}/timeline?before= — biến động 1 két, mới nhất trước."""
    key = request.match_info["key"]
    viewer = await _viewer(request)
    if viewer is not None and key != f"user:{viewer.lower()}":
        return web.json_response({"ok": False, "error": "Chỉ văn phòng xem được két người khác"}, status=403)
    try:
        before = float(request.query.get("before", "") or 0) or None
    except ValueError:
        before = None
    data = await asyncio.to_thread(cashbox_timeline, key, time.time(), 300, before)
    return web.json_response(data, status=200 if data.get("ok") else 404)


def _norm_box(key: str) -> str | None:
    """Chuẩn hoá khoá két nhập tay ('User:Tri ' → 'user:tri'); sai dạng → None."""
    key = (key or "").strip()
    if key in BOX_NAMES:
        return key
    low = key.lower()
    if low.startswith("user:"):
        u = low[5:].strip()
        return f"user:{u}" if u else None
    if low.startswith("tg:"):
        t = low[3:].strip()
        return f"tg:{t}" if t.isdigit() else None
    return None


async def cashbox_transfer_handler(request: web.Request):
    """POST /api/cashbox/transfer {from_box, to_box, amount, note} — văn phòng."""
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được chuyển tiền két"}, status=403)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return web.json_response({"ok": False, "error": "Body không hợp lệ"}, status=400)
    from_box = _norm_box(str(body.get("from_box") or ""))
    to_box = _norm_box(str(body.get("to_box") or ""))
    note = str(body.get("note") or "").strip()
    try:
        amount = int(round(float(body.get("amount") or 0)))
    except (TypeError, ValueError, OverflowError):
        amount = 0
    if amount <= 0:
        return web.json_response({"ok": False, "error": "Số tiền phải > 0"}, status=400)
    if not from_box or not to_box or from_box == to_box:
        return web.json_response({"ok": False, "error": "Két nguồn/đích không hợp lệ"}, status=400)
    actor = str(request.get("web_user") or "")

    def _run():
        conn = get_connection()
        try:
            return cashbox_store.add_transfer(conn, from_box, to_box, amount, note, actor)
        finally:
            conn.close()

    async with _transfer_lock:   # check số dư + insert phải là 1 khối
        now = time.time()
        exists = await asyncio.to_thread(box_exists, to_box, now)
        if not exists:
            return web.json_response({"ok": False, "error": "Két đích không tồn tại"}, status=400)
        balance = await asyncio.to_thread(cashbox_balance, from_box, now)
        if amount > balance:
            return web.json_response(
                {"ok": False, "error": f"Két nguồn chỉ còn {balance:,}đ — không đủ {amount:,}đ".replace(",", ".")},
                status=400)
        transfer = await asyncio.to_thread(_run)
        cashbox_store.invalidate_cache()
    _emit_changed()
    return web.json_response({"ok": True, "transfer": transfer})


async def cashbox_transfer_delete_handler(request: web.Request):
    """POST /api/cashbox/transfer/{id}/delete — admin, hoàn tác 1 lần chuyển."""
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá lần chuyển"}, status=403)
    try:
        transfer_id = int(request.match_info["id"])
    except ValueError:
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    def _run():
        conn = get_connection()
        try:
            return cashbox_store.delete_transfer(conn, transfer_id)
        finally:
            conn.close()
    ok = await asyncio.to_thread(_run)
    if not ok:
        return web.json_response({"ok": False, "error": "Không tìm thấy lần chuyển"}, status=404)
    cashbox_store.invalidate_cache()
    _emit_changed()
    return web.json_response({"ok": True})


async def cashbox_withdraw_handler(request: web.Request):
    """POST /api/cashbox/withdraw {box?, amount, note} — văn phòng rút tiền khỏi két.

    Tiền RA khỏi hệ két (về EXTERNAL, giống trả NCC nhưng thủ công).
    Admin rút được két bất kỳ; user văn phòng thường chỉ rút được két mình.
    """
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được thu hồi tiền két"}, status=403)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return web.json_response({"ok": False, "error": "Body không hợp lệ"}, status=400)
    web_user = str(request.get("web_user") or "").strip().lower()
    # Yêu cầu đăng nhập: khi WEB_AUTH tắt, web_user rỗng → guard "chỉ két mình" bị bỏ
    # và actor rỗng. Chặn hẳn (như purchase_pay) để không rút két bất kỳ vô danh.
    if not web_user:
        return web.json_response({"ok": False, "error": "Cần đăng nhập để thu hồi tiền"}, status=401)
    box = str(body.get("box") or "").strip()
    if not box:
        box = f"user:{web_user}" if web_user else ""
    else:
        nb = _norm_box(box)
        if nb:
            box = nb
    if not box:
        return web.json_response({"ok": False, "error": "Không xác định được két nguồn"}, status=400)
    if not await is_admin_request(request) and web_user:
        if box != f"user:{web_user}":
            return web.json_response({"ok": False, "error": "Chỉ thu hồi được két của mình"}, status=403)
    note = str(body.get("note") or "").strip()
    try:
        amount = int(round(float(body.get("amount") or 0)))
    except (TypeError, ValueError, OverflowError):
        amount = 0
    if amount <= 0:
        return web.json_response({"ok": False, "error": "Số tiền phải > 0"}, status=400)
    actor = web_user

    def _run():
        conn = get_connection()
        try:
            return cashbox_store.add_transfer(conn, box, cashbox_store.EXTERNAL, amount, note, actor)
        finally:
            conn.close()

    async with _transfer_lock:
        now = time.time()
        exists = await asyncio.to_thread(box_exists, box, now)
        if not exists:
            return web.json_response({"ok": False, "error": "Két nguồn không tồn tại"}, status=400)
        balance = await asyncio.to_thread(cashbox_balance, box, now)
        if amount > balance:
            return web.json_response(
                {"ok": False, "error": f"Két chỉ còn {balance:,}đ — không đủ {amount:,}đ".replace(",", ".")},
                status=400)
        transfer = await asyncio.to_thread(_run)
        cashbox_store.invalidate_cache()
    _emit_changed()
    return web.json_response({"ok": True, "transfer": transfer})


def _emit_changed() -> None:
    try:
        from server_app.realtime import emit_cashbox_changed
        emit_cashbox_changed()
    except Exception:  # noqa: BLE001 — không có loop (test) thì bỏ qua
        pass
