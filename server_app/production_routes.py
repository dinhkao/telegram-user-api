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
import time
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
    set_kind,
    add_number,
    set_bang,
    delete_slip,
    set_lock_override,
)
from production_store.domain import parse_report, compute_report
from server_app.production_lock import is_locked as _prod_is_locked, locked_error as _prod_locked_error, lock_at as _prod_lock_at
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
        rep = {}
        boxed = 0
        bcodes: list = []
        if slip:
            from production_store.report_rows import report_summaries
            from inventory_store import sum_boxes_by_source, codes_by_source
            rep = report_summaries(conn, [thread_id]).get(slip["thread_id"]) or {}
            boxed = sum_boxes_by_source(conn, [thread_id]).get(slip["thread_id"]) or 0
            if not (slip.get("sp_name") or "").strip():   # chưa chọn SP → mã thùng đã nhập
                bcodes = codes_by_source(conn, [thread_id]).get(slip["thread_id"]) or []
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
        "kind": slip.get("kind") or "san_xuat",
        "updated_at": slip.get("updated_at"),
        # Khoá phiếu: tự khoá 24h sau khi tạo; admin ghi đè. locked = hiệu lực cuối.
        "locked": _prod_is_locked(slip),
        "lock_override": slip.get("lock_override"),
        "lock_at": _prod_lock_at(slip),   # ISO tạo+24h khi còn đếm ngược (else None)
        # báo cáo thợ (card SX): luôn có mặt để realtime patch GHI ĐÈ giá trị cũ
        "report_total": rep.get("total") or 0,
        "report_workers": rep.get("workers") or [],
        "report_notes": rep.get("notes") or [],
        "boxed_total": boxed,   # tổng NHẬP THÙNG thật (Σ quantity thùng từ phiếu, bỏ số nhập tay)
        "boxed_codes": bcodes,  # mã SP các thùng đã nhập (chỉ khi phiếu CHƯA chọn SP) → hiện ở title
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
    kind = request.query.get("kind") or None
    if kind not in ("san_xuat", "dong_goi"):
        kind = None
    # day = 'YYYYMMDD' (hoặc 'YYYY-MM-DD') → lọc phiếu tạo trong đúng 1 ngày
    day = "".join(ch for ch in (request.query.get("day") or "") if ch.isdigit())[:8] or None
    # mismatch=1 → chỉ phiếu SX từ 2026-07-10 có báo cáo LỆCH tổng nhập thùng >1%
    mismatch = request.query.get("mismatch") == "1"

    def _run():
        conn = _conn()
        try:
            create_production_table(conn)
            total = count_slips(conn, kind=kind, day=day, mismatch=mismatch)
            slips = list_slips(conn, limit=limit, offset=offset, kind=kind, day=day, mismatch=mismatch)
            from production_store.report_rows import report_summaries
            from inventory_store import (sum_boxes_by_source, codes_by_source,
                                         consumed_materials_by_source, boxed_by_source_product)
            _ids = [s["thread_id"] for s in slips]
            reports = report_summaries(conn, _ids)
            boxed_sums = sum_boxes_by_source(conn, _ids)
            # phiếu CHƯA chọn SP → lấy mã SP các thùng đã nhập để hiện ở title
            _need = [s["thread_id"] for s in slips if not (s.get("sp_name") or "").strip()]
            codes_map = codes_by_source(conn, _need) if _need else {}
            # phiếu ĐÓNG GÓI: TÁCH theo từng SP thành phẩm, mỗi SP kèm NL của nó.
            # 1 SP → NL thật (tiêu hao); nhiều SP → NL theo công thức từng SP (allocation
            # gắn phiếu chứ không gắn SP nên không tách thật được).
            from recipe_store import recipe_needs
            from product_store import resolve_code
            _unit_cache: dict = {}
            def _unit(code):   # đơn vị của 1 mã SP/NL (cache trong request)
                if code not in _unit_cache:
                    p = resolve_code(conn, code)
                    _unit_cache[code] = (p.get("unit") if p else None) or "cây"
                return _unit_cache[code]
            _pack = [s["thread_id"] for s in slips if (s.get("kind") or "san_xuat") == "dong_goi"]
            pack_boxes = boxed_by_source_product(conn, _pack) if _pack else {}
            pack_actual = consumed_materials_by_source(conn, _pack) if _pack else {}
            pack_items_map: dict = {}
            for tid in _pack:
                items = pack_boxes.get(tid) or []
                act = pack_actual.get(tid) or {}
                if len(items) == 1:
                    mats = [{"code": m["code"], "amount": m["amount"], "unit": _unit(m["code"])}
                            for m in (act.get("materials") or [])]
                    out_items = [{"product": items[0]["code"], "qty": items[0]["qty"],
                                  "unit": _unit(items[0]["code"]), "materials": mats}]
                else:
                    out_items = []
                    for it in items:
                        needs = recipe_needs(conn, it["code"], it["qty"])
                        out_items.append({"product": it["code"], "qty": it["qty"], "unit": _unit(it["code"]),
                                          "materials": [{"code": n["code"], "amount": n["amount"], "unit": _unit(n["code"])} for n in needs]})
                pack_items_map[tid] = {"by": act.get("by"), "items": out_items}
        finally:
            conn.close()
        for s in slips:
            s.update(_progress(s))
            rep = reports.get(s["thread_id"]) or {}
            s["report_total"] = rep.get("total") or 0
            s["report_workers"] = rep.get("workers") or []
            s["report_notes"] = rep.get("notes") or []
            s["boxed_total"] = boxed_sums.get(s["thread_id"]) or 0
            if not (s.get("sp_name") or "").strip():
                s["boxed_codes"] = codes_map.get(s["thread_id"]) or []
            if (s.get("kind") or "san_xuat") == "dong_goi":
                pk = pack_items_map.get(s["thread_id"]) or {}
                s["pack_by"] = pk.get("by")
                s["pack_items"] = pk.get("items") or []
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
            slip = get_slip(conn, thread_id)
            if slip:
                # số thùng đã tạo từ phiếu — UI khoá đổi loại + chặn xoá theo nó
                from inventory_store import count_boxes_by_source, sum_boxes_by_source
                slip["box_count"] = count_boxes_by_source(conn, thread_id)
                slip["boxed_total"] = sum_boxes_by_source(conn, [thread_id]).get(thread_id) or 0
                slip["locked"] = _prod_is_locked(slip)   # khoá phiếu (24h / admin) cho UI
            return slip
        finally:
            conn.close()
    slip = await asyncio.to_thread(_run)
    if not slip:
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu"}, status=404)
    slip.update(_progress(slip))
    return web.json_response({"ok": True, "slip": slip})


async def production_catalog_handler(request: web.Request):
    """Danh mục sản phẩm cho UI (chọn SP khi tạo/sửa phiếu) — nguồn chính = bảng
    products (mam/lượng từ cột prod_mam/prod_luong, fallback SP_INFO); kèm mã
    legacy chỉ có trong SP_INFO/PRODUCT_CODES (chưa vào danh mục)."""
    def _run():
        conn = _conn()
        try:
            from product_store import get_all_products
            prods = get_all_products(conn)
        finally:
            conn.close()
        out = []
        for p in prods:
            info = SP_INFO.get(p["code"], {})
            out.append({
                "id": p.get("id"), "code": p["code"], "name": p.get("name") or "",
                "mam": p.get("prod_mam") if p.get("prod_mam") is not None else info.get("mam"),
                "luong": p.get("prod_luong") if p.get("prod_luong") is not None else info.get("luong"),
                "cay_1_chao": CAY_TRONG_1_CHAO.get(p["code"]),
            })
        known = {p["code"] for p in out}
        for code in list(SP_INFO.keys()) + list(PRODUCT_CODES):
            if code not in known:
                known.add(code)
                info = SP_INFO.get(code, {})
                out.append({"id": None, "code": code, "name": "", "mam": info.get("mam"),
                            "luong": info.get("luong"), "cay_1_chao": CAY_TRONG_1_CHAO.get(code)})
        return out
    products = await asyncio.to_thread(_run)
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
                from production_store.defaults import production_defaults
                mam, luong = production_defaults(conn, product)
                set_sp(conn, thread_id, product, mam, luong)
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
    lk = await _prod_locked_error(request, thread_id)
    if lk:
        return lk

    def _run():
        conn = _conn()
        try:
            from production_store.defaults import production_defaults
            mam, luong = production_defaults(conn, code)
            set_sp(conn, thread_id, code, mam, luong)
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
    lk = await _prod_locked_error(request, thread_id)
    if lk:
        return lk

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
    lk = await _prod_locked_error(request, thread_id)
    if lk:
        return lk

    def _run():
        conn = _conn()
        try:
            set_note(conn, thread_id, note)
        finally:
            conn.close()
    await asyncio.to_thread(_run)
    _emit(thread_id)
    return web.json_response({"ok": True})


async def production_set_kind_handler(request: web.Request):
    """Đổi loại phiếu: 'san_xuat' (có bảng báo cáo thợ) | 'dong_goi' (không).
    KHOÁ khi phiếu đã nhập ≥1 thùng — loại chi phối logic nguyên liệu lúc tạo thùng
    (sản xuất: KHÔNG cần NL; đóng gói: BẮT BUỘC công thức + đủ NL), đổi sau khi đã
    tạo thùng làm dữ liệu tiêu hao vô nghĩa."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    kind = str(body.get("kind") or "san_xuat")
    lk = await _prod_locked_error(request, thread_id)
    if lk:
        return lk

    def _run():
        conn = _conn()
        try:
            from inventory_store import count_boxes_by_source
            n = count_boxes_by_source(conn, thread_id)
            if n > 0:
                return n
            set_kind(conn, thread_id, kind)
            return 0
        finally:
            conn.close()
    n_boxes = await asyncio.to_thread(_run)
    if n_boxes:
        return web.json_response(
            {"ok": False, "error": f"Phiếu đã nhập {n_boxes} thùng — không đổi loại được nữa"}, status=400)
    _emit(thread_id)
    return web.json_response({"ok": True, "kind": "dong_goi" if kind == "dong_goi" else "san_xuat"})


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
    lk = await _prod_locked_error(request, thread_id)
    if lk:
        return lk

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
    me = _web_actor(request, body)
    plk = await _prod_locked_error(request, thread_id)   # phiếu đã khoá 24h → cấm lưu báo cáo
    if plk:
        return plk
    lk = _lock_info(thread_id)
    if lk and not _is_lock_mine(lk, me, str(body.get("sid") or "")):   # phiên khác giữ khoá → chặn ghi đè
        return web.json_response({"ok": False, "error": f"Đang được {lk['user']} chỉnh sửa", "holder": lk["user"]}, status=409)
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
    # Đẩy báo cáo lên Google Sheet (tab theo ngày) — TẮT mặc định (config.PRODUCTION_SHEET_SYNC)
    from server_app.config import PRODUCTION_SHEET_SYNC
    if PRODUCTION_SHEET_SYNC:
        from server_app.production_sheets import push_report
        sheet = await push_report(thread_id, text)
    else:
        sheet = {"disabled": True}
    return web.json_response({"ok": True, "sheet": sheet, **result})


async def production_delete_handler(request: web.Request):
    """Xoá phiếu SX — CHỈ admin, và CHỈ khi phiếu không còn thùng nào tạo từ nó."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá phiếu sản xuất"}, status=403)
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            # CẤM xoá nếu phiếu đã tạo ra thùng (còn nguồn gốc kho) — gỡ thùng trước.
            from inventory_store import count_boxes_by_source, release_production_consumption
            n = count_boxes_by_source(conn, thread_id)
            if n > 0:
                return n
            # Hoàn nốt nguyên liệu còn trừ cho phiếu này (residue sau khi xoá từng
            # thùng — không hoàn thì allocation mồ côi, NL mất kho vĩnh viễn)
            release_production_consumption(conn, thread_id)
            delete_slip(conn, thread_id)
            return 0
        finally:
            conn.close()
    n_boxes = await asyncio.to_thread(_run)
    if n_boxes:
        return web.json_response(
            {"ok": False, "error": f"Không xoá được — phiếu đã tạo {n_boxes} thùng. Xoá các thùng đó trước."},
            status=400,
        )
    from server_app.realtime import emit_productions_changed
    emit_productions_changed()
    return web.json_response({"ok": True})


# ─── helpers ─────────────────────────────────────────────────────────────────
def _compute(thread_id, text: str) -> dict:
    parsed = parse_report(text)
    product_code = parsed.get("product_code")
    conn = _conn()
    try:
        if not product_code and thread_id is not None:
            slip = get_slip(conn, thread_id)
            if slip and slip.get("sp_name"):
                product_code = slip["sp_name"].upper()
        from production_store.defaults import production_defaults
        so_cay_1_mam = (production_defaults(conn, product_code)[0] or 0) if product_code else 0
    finally:
        conn.close()
    return compute_report({**parsed, "product_code": product_code}, so_cay_1_mam)


def _emit(thread_id) -> None:
    from server_app.realtime import emit_production_changed
    emit_production_changed(thread_id)


async def _set_slip_lock(request: web.Request, value: str):
    """Admin đặt lock_override cho phiếu ('locked' | 'unlocked')."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin khoá/mở phiếu được"}, status=403)

    def _run():
        conn = _conn()
        try:
            set_lock_override(conn, thread_id, value)
        finally:
            conn.close()
    await asyncio.to_thread(_run)
    _emit(thread_id)
    return web.json_response({"ok": True, "locked": value == "locked"})


async def production_slip_lock_handler(request: web.Request):
    """Admin KHOÁ phiếu SX (cấm sửa, chỉ trao đổi). POST /api/production/{id}/slip-lock."""
    return await _set_slip_lock(request, "locked")


async def production_slip_unlock_handler(request: web.Request):
    """Admin MỞ KHOÁ phiếu SX (cho sửa lại). POST /api/production/{id}/slip-unlock."""
    return await _set_slip_lock(request, "unlocked")


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


# ─── Khoá SỬA báo cáo: 1 phiếu SX chỉ 1 người sửa cùng lúc (in-memory, có TTL) ──
_report_locks: dict[int, dict] = {}
_LOCK_TTL = 45.0                      # hết hạn nếu client ngừng heartbeat (~mỗi 20s)


def _report_user_key(user: str | None) -> str:
    """Khoá so sánh user ổn định, không phụ thuộc hoa/thường hay khoảng trắng."""
    return " ".join(str(user or "").split()).casefold()


def _report_session_key(sid: str | None) -> str:
    return str(sid or "__legacy__")


def _same_report_user(lk: dict, user: str) -> bool:
    return str(lk.get("user_key") or _report_user_key(lk.get("user"))) == _report_user_key(user)


def _lock_info(thread_id: int) -> dict | None:
    """Khoá còn hiệu lực của phiếu (None nếu trống/hết hạn). Dọn khoá hết hạn."""
    lk = _report_locks.get(thread_id)
    if not lk:
        return None

    # Tương thích khoá cũ tạo trước khi hỗ trợ nhiều tab cho cùng một user.
    sessions = lk.get("sessions")
    if not isinstance(sessions, dict):
        sessions = {_report_session_key(lk.get("sid")): float(lk.get("at") or 0)}
        lk["sessions"] = sessions
    lk["user_key"] = str(lk.get("user_key") or _report_user_key(lk.get("user")))

    now = time.monotonic()
    for session, heartbeat_at in list(sessions.items()):
        if (now - float(heartbeat_at or 0)) >= _LOCK_TTL:
            sessions.pop(session, None)
    if not sessions:
        _report_locks.pop(thread_id, None)
        # TTL trước đây chỉ xoá trong RAM nên client đang xem vẫn giữ badge
        # "X đang sửa" vô thời hạn. Phát trạng thái nhả để mọi màn hình đồng bộ.
        from server_app.realtime import emit_report_lock
        emit_report_lock(thread_id, None)
        return None
    return lk


def _lock_holder(thread_id: int) -> str | None:
    lk = _lock_info(thread_id)
    return lk["user"] if lk else None


def _is_lock_mine(lk: dict | None, me: str, sid: str) -> bool:
    """Phiên này đã tham gia khoá của đúng user hay chưa."""
    if not lk or not _same_report_user(lk, me):
        return False
    sessions = lk.get("sessions")
    if isinstance(sessions, dict):
        return _report_session_key(sid) in sessions
    return _report_session_key(lk.get("sid")) == _report_session_key(sid)


async def production_report_lock_handler(request: web.Request):
    """Xin/gia hạn khoá sửa báo cáo. Body {user?, sid} — sid = mã phiên mỗi tab.
    Trả {holder, mine}. Các tab của cùng user cùng tham gia một khoá."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    me = _web_actor(request, body)
    sid = str(body.get("sid") or "")
    lk = _lock_info(thread_id)
    if lk and not _same_report_user(lk, me):
        return web.json_response({"ok": True, "holder": lk["user"], "mine": False})
    was_free = lk is None
    if lk is None:
        lk = {"user": me, "user_key": _report_user_key(me), "sessions": {}}
        _report_locks[thread_id] = lk
    lk["sessions"][_report_session_key(sid)] = time.monotonic()
    if was_free:   # chỉ phát khi ĐỔI trạng thái (tránh spam theo heartbeat)
        from server_app.realtime import emit_report_lock
        emit_report_lock(thread_id, me)
    return web.json_response({"ok": True, "holder": me, "mine": True})


async def production_report_lock_status_handler(request: web.Request):
    """Xem AI đang giữ khoá — KHÔNG xin khoá. Badge '✏️ X đang sửa' ở trang chi tiết."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    return web.json_response({"ok": True, "holder": _lock_holder(thread_id)})


async def production_report_unlock_handler(request: web.Request):
    """Nhả khoá (chỉ khi mình đang giữ)."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    me = _web_actor(request, body)
    sid = str(body.get("sid") or "")
    lk = _lock_info(thread_id)
    if _is_lock_mine(lk, me, sid):
        lk["sessions"].pop(_report_session_key(sid), None)
        if not lk["sessions"]:
            _report_locks.pop(thread_id, None)
            from server_app.realtime import emit_report_lock
            emit_report_lock(thread_id, None)
    return web.json_response({"ok": True})


async def production_report_draft_handler(request: web.Request):
    """Người đang giữ khoá gửi bản nháp bảng → phát cho người XEM thấy trực tiếp (không lưu)."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    me = _web_actor(request, body)
    sid = str(body.get("sid") or "")
    if not _is_lock_mine(_lock_info(thread_id), me, sid):   # chỉ PHIÊN đang giữ được phát nháp
        return web.json_response({"ok": False}, status=409)
    _report_locks[thread_id]["sessions"][_report_session_key(sid)] = time.monotonic()
    from server_app.realtime import emit_report_draft
    emit_report_draft(thread_id, {
        "rows": body.get("rows") or [], "date": body.get("date"),
        "start": body.get("start"), "end": body.get("end"), "by": me, "sid": sid,
    })
    return web.json_response({"ok": True})
