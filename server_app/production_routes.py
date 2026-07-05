"""HTTP handlers cho phiếu sản xuất (webapp) — /api/production*.

Layer mỏng trên production_store (+ domain parser) và bot_core.config (catalog).
Tạo phiếu mới sẽ mở forum topic trong PRODUCTION_GROUP_ID (dùng lại
command_handlers.production_commands._create_forum_topic). Ghi xong phát realtime
production_changed/productions_changed (server_app/realtime). Đăng ký ở app_factory.

Kết nối: production_store, production_store.domain, bot_core.config,
server_app.state (telethon client), server_app.realtime, server_app.production_sheets.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

from aiohttp import web

from bot_core.config import SP_INFO, PRODUCT_CODES, CAY_TRONG_1_CHAO, PRODUCTION_GROUP_ID
from production_store import (
    create_production_table,
    get_slip,
    list_slips,
    count_slips,
    upsert_slip,
    set_sp,
    set_target,
    set_note,
    add_number,
    set_bang,
    delete_slip,
)
from production_store.domain import parse_report, compute_report
from utils.db import get_connection

_VN_TZ = timezone(timedelta(hours=7))


def _conn():
    return get_connection()


def _thread_id(request: web.Request) -> int | None:
    try:
        return int(request.match_info.get("thread_id", ""))
    except (ValueError, TypeError):
        return None


def _progress(slip: dict) -> dict:
    total = slip.get("total") or 0
    target = slip.get("sx_target")
    pct = round(total / target * 100) if target else None
    return {"total": total, "target": target, "pct": pct}


def build_production_row(thread_id) -> dict | None:
    """Row gọn cho danh sách + realtime (mở conn riêng — gọi được từ nền)."""
    conn = _conn()
    try:
        slip = get_slip(conn, thread_id)
    finally:
        conn.close()
    if not slip:
        return None
    return {
        "thread_id": slip["thread_id"],
        "date": slip.get("date"),
        "sp_name": slip.get("sp_name"),
        "sp_mam": slip.get("sp_mam"),
        "sx_target": slip.get("sx_target"),
        "total": slip.get("total") or 0,
        "ghi_chu": slip.get("ghi_chu"),
        "updated_at": slip.get("updated_at"),
        **_progress(slip),
    }


# ─── reads ───────────────────────────────────────────────────────────────────
async def production_list_handler(request: web.Request):
    try:
        page = max(1, int(request.query.get("page", "1")))
    except (ValueError, TypeError):
        page = 1
    try:
        limit = max(1, min(100, int(request.query.get("limit", "20"))))
    except (ValueError, TypeError):
        limit = 20
    offset = (page - 1) * limit

    def _run():
        conn = _conn()
        try:
            create_production_table(conn)
            total = count_slips(conn)
            slips = list_slips(conn, limit=limit, offset=offset)
        finally:
            conn.close()
        for s in slips:
            s.update(_progress(s))
        return slips, total
    slips, total = await asyncio.to_thread(_run)
    return web.json_response({
        "ok": True, "slips": slips, "total": total, "page": page,
        "limit": limit, "total_pages": max(1, (total + limit - 1) // limit),
    })


async def production_detail_handler(request: web.Request):
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            return get_slip(conn, thread_id)
        finally:
            conn.close()
    slip = await asyncio.to_thread(_run)
    if not slip:
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu"}, status=404)
    slip.update(_progress(slip))
    return web.json_response({"ok": True, "slip": slip})


async def production_catalog_handler(request: web.Request):
    """Danh mục sản phẩm cho UI (chọn SP khi tạo/sửa phiếu)."""
    products = [
        {"code": code, "mam": info.get("mam"), "luong": info.get("luong"),
         "cay_1_chao": CAY_TRONG_1_CHAO.get(code)}
        for code, info in SP_INFO.items()
    ]
    # kèm các mã chỉ có trong PRODUCT_CODES (chưa có SP_INFO)
    known = {p["code"] for p in products}
    for code in PRODUCT_CODES:
        if code not in known:
            products.append({"code": code, "mam": None, "luong": None,
                             "cay_1_chao": CAY_TRONG_1_CHAO.get(code)})
    return web.json_response({"ok": True, "products": products})


# ─── writes ──────────────────────────────────────────────────────────────────
async def production_create_handler(request: web.Request):
    """Tạo phiếu mới: mở forum topic trong group SX rồi lưu slip."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    from server_app import state
    client = state._client
    if client is None:
        return web.json_response({"ok": False, "error": "Telegram client chưa sẵn sàng"}, status=503)
    from command_handlers.production_commands import _create_forum_topic

    now = datetime.now(_VN_TZ)
    date_code = now.strftime("%Y%m%d%H%M%S")
    thread_id = await _create_forum_topic(client, PRODUCTION_GROUP_ID, date_code)
    if not thread_id:
        return web.json_response({"ok": False, "error": "Không tạo được topic"}, status=502)

    product = str(body.get("product") or "").strip().upper() or None

    def _run():
        conn = _conn()
        try:
            create_production_table(conn)
            upsert_slip(conn, thread_id, date=now.strftime("%d/%m/%Y %H:%M"), date_code=date_code)
            if product:
                info = SP_INFO.get(product, {})
                set_sp(conn, thread_id, product, info.get("mam"), info.get("luong"))
        finally:
            conn.close()
    await asyncio.to_thread(_run)

    from server_app.realtime import emit_productions_changed
    emit_productions_changed()
    # Log lịch sử thao tác: tạo phiếu SX
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.production_created", async_log_event(
        "production.created", scope="production", thread_id=thread_id,
        actor_type="web_user" if request.get("web_user") else "http_client",
        actor_id=request.get("web_user") or request.remote,
        source="production.created", payload={"product": product}))
    return web.json_response({"ok": True, "thread_id": thread_id})


async def production_set_product_handler(request: web.Request):
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    code = str(body.get("product") or "").strip().upper()
    if not code:
        return web.json_response({"ok": False, "error": "Thiếu mã sản phẩm"}, status=400)

    def _run():
        conn = _conn()
        try:
            info = SP_INFO.get(code, {})
            set_sp(conn, thread_id, code, info.get("mam"), info.get("luong"))
        finally:
            conn.close()
    await asyncio.to_thread(_run)
    _emit(thread_id)
    return web.json_response({"ok": True})


async def production_set_target_handler(request: web.Request):
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
        target = int(body.get("target"))
    except (Exception, TypeError, ValueError):
        return web.json_response({"ok": False, "error": "Mục tiêu SX không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            set_target(conn, thread_id, target)
        finally:
            conn.close()
    await asyncio.to_thread(_run)
    _emit(thread_id)
    return web.json_response({"ok": True})


async def production_set_note_handler(request: web.Request):
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    note = str(body.get("note") or "")

    def _run():
        conn = _conn()
        try:
            set_note(conn, thread_id, note)
        finally:
            conn.close()
    await asyncio.to_thread(_run)
    _emit(thread_id)
    return web.json_response({"ok": True})


async def production_add_number_handler(request: web.Request):
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
        amount = float(body.get("amount"))
    except (Exception, TypeError, ValueError):
        return web.json_response({"ok": False, "error": "Số lượng không hợp lệ"}, status=400)
    note = str(body.get("note") or "").strip()
    actor = _web_actor(request, body)

    def _run():
        conn = _conn()
        try:
            slip = get_slip(conn, thread_id)
            if not slip or not slip.get("sp_name"):
                return None
            return add_number(conn, thread_id, amount, note, by=actor)
        finally:
            conn.close()
    total = await asyncio.to_thread(_run)
    if total is None:
        return web.json_response({"ok": False, "error": "Chưa có sản phẩm, chưa nhập hàng được"}, status=400)
    _emit(thread_id)
    # đồng bộ Google Sheet (best-effort, gated) — import row cho số lượng nhận
    from server_app.production_sheets import sync_number_bg
    sync_number_bg(thread_id, amount, note, request)
    return web.json_response({"ok": True, "total": total})


async def production_report_parse_handler(request: web.Request):
    """Xem trước báo cáo: parse + compute, KHÔNG lưu (dùng khi dán để preview)."""
    thread_id = _thread_id(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    text = str(body.get("text") or "")
    return web.json_response({"ok": True, **_compute(thread_id, text)})


async def production_report_save_handler(request: web.Request):
    """Lưu báo cáo: parse + compute + set_bang, phát realtime."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    text = str(body.get("text") or "")
    result = _compute(thread_id, text)
    if not result["rows"]:
        return web.json_response({"ok": False, "error": "Không phân tích được dữ liệu"}, status=400)

    def _run():
        conn = _conn()
        try:
            set_bang(conn, thread_id, {
                "product_code": result["product_code"],
                "so_cay_1_mam": result["so_cay_1_mam"],
                "date": result.get("date"),
                "start": result.get("start"),
                "end": result.get("end"),
                "rows": result["rows"],
                "grand_total": result["grand_total"],
                "updated_at": datetime.now(_VN_TZ).isoformat(),
            })
        finally:
            conn.close()
    await asyncio.to_thread(_run)
    _emit(thread_id)
    # Đẩy báo cáo lên Google Sheet (tab theo ngày) — CHỜ kết quả để báo rõ cho user
    from server_app.production_sheets import push_report
    sheet = await push_report(thread_id, text)
    return web.json_response({"ok": True, "sheet": sheet, **result})


async def production_delete_handler(request: web.Request):
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            delete_slip(conn, thread_id)
        finally:
            conn.close()
    await asyncio.to_thread(_run)
    from server_app.realtime import emit_productions_changed
    emit_productions_changed()
    return web.json_response({"ok": True})


# ─── helpers ─────────────────────────────────────────────────────────────────
def _compute(thread_id, text: str) -> dict:
    parsed = parse_report(text)
    product_code = parsed.get("product_code")
    if not product_code and thread_id is not None:
        conn = _conn()
        try:
            slip = get_slip(conn, thread_id)
        finally:
            conn.close()
        if slip and slip.get("sp_name"):
            product_code = slip["sp_name"].upper()
    so_cay_1_mam = SP_INFO.get(product_code, {}).get("mam", 0) if product_code else 0
    return compute_report({**parsed, "product_code": product_code}, so_cay_1_mam)


def _emit(thread_id) -> None:
    from server_app.realtime import emit_production_changed
    emit_production_changed(thread_id)


def _web_actor(request: web.Request, body: dict | None = None) -> str:
    """Tên người thao tác: web_user (middleware) → body['user'] → 'web'."""
    user = request.get("web_user")
    if isinstance(user, dict):
        return str(user.get("display_name") or user.get("name") or user.get("username") or "web")
    if user:
        return str(user)
    if body and body.get("user"):
        return str(body["user"])
    return "web"
