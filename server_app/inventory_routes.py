"""HTTP handlers kho thùng (webapp) — /api/inventory* + nhập/xuất thùng.

Nhập thùng từ phiếu SX (POST /api/production/{id}/boxes) → tạo box rows + append
numbers[] cho slip (total/progress tự đúng). Xem tồn theo product (GET /api/inventory,
/api/inventory/{code}). Xuất/thu thùng cho đơn (POST /api/order/{id}/allocate|release).

Nối: inventory_store, production_store (add_number/get_slip), server_app.realtime,
server_app.production_routes (_web_actor), utils.db. Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from inventory_store import (
    create_inventory_table,
    migrate_inventory_table,
    create_allocations_table,
    migrate_legacy_allocations,
    add_boxes,
    list_boxes,
    product_summary,
    get_box,
    update_box,
    set_disabled,
    allocate_picks,
    list_order_allocations,
    list_box_allocations,
    get_allocation,
    delete_allocation,
    summarize,
)
from production_store import get_slip, add_number, set_total
from server_app.production_routes import _web_actor
from utils.db import get_connection


def _conn():
    return get_connection()


def _ensure(conn):
    """Tạo bảng + migrate (cột mới như disabled/mfg_date, bảng box_allocations)."""
    create_inventory_table(conn)
    migrate_inventory_table(conn)
    create_allocations_table(conn)
    migrate_legacy_allocations(conn)


def _thread_id(request: web.Request) -> int | None:
    try:
        return int(request.match_info.get("thread_id", ""))
    except (ValueError, TypeError):
        return None


def _product_code(request: web.Request) -> str:
    return str(request.match_info.get("product_code", "")).strip().upper()


# ─── nhập thùng (từ phiếu SX) ─────────────────────────────────────────────────
async def production_add_boxes_handler(request: web.Request):
    """Nhập 1 đợt = N thùng, mỗi thùng số cây tự do. Mã thùng tự sinh theo product."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    raw = body.get("boxes")
    if not isinstance(raw, list) or not raw:
        return web.json_response({"ok": False, "error": "Thiếu danh sách thùng"}, status=400)
    quantities = []
    for item in raw:
        try:
            q = float(item.get("quantity") if isinstance(item, dict) else item)
        except (TypeError, ValueError):
            return web.json_response({"ok": False, "error": "Số lượng thùng không hợp lệ"}, status=400)
        if q <= 0:
            return web.json_response({"ok": False, "error": "Số lượng thùng phải > 0"}, status=400)
        quantities.append(q)
    note = str(body.get("note") or "").strip()
    mfg_date = str(body.get("mfg_date") or "").strip() or None
    actor = _web_actor(request, body)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            slip = get_slip(conn, thread_id)
            if not slip or not slip.get("sp_name"):
                return None, None
            code = str(slip["sp_name"]).strip().upper()
            created = add_boxes(conn, code, quantities, source_thread_id=thread_id, by=actor, note=note, mfg_date=mfg_date)
            # đồng bộ slip.total/numbers/progress: 1 entry/thùng (note = mã thùng)
            total = slip.get("total") or 0
            for box in created:
                total = add_number(conn, thread_id, box["quantity"], f"📦 {box['box_code']}", by=actor)
            return created, total
        finally:
            conn.close()
    created, total = await asyncio.to_thread(_run)
    if created is None:
        return web.json_response({"ok": False, "error": "Chưa có sản phẩm, chưa nhập thùng được"}, status=400)
    from server_app.realtime import emit_production_changed
    emit_production_changed(thread_id)
    return web.json_response({"ok": True, "boxes": created, "total": total})


async def production_boxes_list_handler(request: web.Request):
    """Các thùng đã nhập ở 1 phiếu SX (mọi status) — cho list + deep-link focus."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            return list_boxes(conn, source_thread_id=thread_id)
        finally:
            conn.close()
    boxes = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "boxes": boxes})


# ─── xem tồn kho ──────────────────────────────────────────────────────────────
async def inventory_list_handler(request: web.Request):
    """Dashboard kho: mỗi product tồn (in_stock) + số thùng đã xuất/đã giao."""
    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            return product_summary(conn)
        finally:
            conn.close()
    products = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "products": products})


async def box_detail_handler(request: web.Request):
    """Chi tiết 1 thùng: info + phiếu SX nguồn (sp_name, ngày) + đơn đã xuất (nếu có)."""
    try:
        box_id = int(request.match_info.get("box_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "box_id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            box = get_box(conn, box_id)
            if not box:
                return None, None, None
            allocs = list_box_allocations(conn, box_id)
            slip = get_slip(conn, box["source_thread_id"]) if box.get("source_thread_id") else None
            return box, slip, allocs
        finally:
            conn.close()
    box, slip, allocs = await asyncio.to_thread(_run)
    if not box:
        return web.json_response({"ok": False, "error": "Không tìm thấy thùng"}, status=404)
    used = sum(a.get("quantity") or 0 for a in allocs)
    box["allocated"] = used
    box["remaining"] = float(box.get("quantity") or 0) - used
    source = None
    if slip:
        source = {"thread_id": slip["thread_id"], "date": slip.get("date"), "sp_name": slip.get("sp_name")}
    return web.json_response({"ok": True, "box": box, "source_slip": source, "allocations": allocs})


async def box_update_handler(request: web.Request):
    """Sửa ghi chú (và/hoặc số cây) của 1 thùng. Trả box sau khi cập nhật."""
    try:
        box_id = int(request.match_info.get("box_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "box_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    note = body.get("note")
    quantity = body.get("quantity")
    mfg_date = body.get("mfg_date")
    kwargs = {}
    if note is not None:
        kwargs["note"] = str(note)
    if mfg_date is not None:
        kwargs["mfg_date"] = str(mfg_date).strip()
    if quantity is not None:
        try:
            q = float(quantity)
        except (TypeError, ValueError):
            return web.json_response({"ok": False, "error": "Số cây không hợp lệ"}, status=400)
        if q <= 0:
            return web.json_response({"ok": False, "error": "Số cây phải > 0"}, status=400)
        kwargs["quantity"] = q
    if not kwargs:
        return web.json_response({"ok": False, "error": "Không có gì để sửa"}, status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            if not get_box(conn, box_id):
                return None
            update_box(conn, box_id, **kwargs)
            return get_box(conn, box_id)
        finally:
            conn.close()
    box = await asyncio.to_thread(_run)
    if not box:
        return web.json_response({"ok": False, "error": "Không tìm thấy thùng"}, status=404)
    return web.json_response({"ok": True, "box": box})


async def box_disable_handler(request: web.Request):
    """Vô hiệu / kích hoạt lại 1 thùng. Vô hiệu = không tính tồn, không phân bổ đơn,
    trừ khỏi tổng phiếu SX nguồn (kích hoạt lại thì cộng vào). Vẫn hiển thị."""
    try:
        box_id = int(request.match_info.get("box_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "box_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    disabled = bool(body.get("disabled", True))
    reason = str(body.get("reason") or "").strip()
    if disabled and not reason:
        return web.json_response({"ok": False, "error": "Nhập lý do vô hiệu thùng"}, status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            box = get_box(conn, box_id)
            if not box:
                return None, None
            was = bool(box.get("disabled"))
            if was == disabled:
                return box, None  # không đổi
            # Cấm vô hiệu thùng đã xuất 1 phần cho đơn — thu hồi khỏi đơn trước
            if disabled and list_box_allocations(conn, box_id):
                return box, "Thùng đã phân bổ vào đơn — thu hồi khỏi đơn trước khi vô hiệu"
            set_disabled(conn, box_id, disabled, reason=reason)
            # Đồng bộ tổng phiếu SX nguồn: vô hiệu → trừ, kích hoạt → cộng
            src = box.get("source_thread_id")
            if src:
                slip = get_slip(conn, src)
                if slip:
                    qty = box.get("quantity") or 0
                    total = (slip.get("total") or 0) + (-qty if disabled else qty)
                    set_total(conn, src, max(0, total))
            return get_box(conn, box_id), None
        finally:
            conn.close()
    box, err = await asyncio.to_thread(_run)
    if err:
        return web.json_response({"ok": False, "error": err}, status=409)
    if not box:
        return web.json_response({"ok": False, "error": "Không tìm thấy thùng"}, status=404)
    src = box.get("source_thread_id")
    if src:
        from server_app.realtime import emit_production_changed
        emit_production_changed(src)
    return web.json_response({"ok": True, "box": box})


async def inventory_detail_handler(request: web.Request):
    """Tồn 1 product: tổng + nhóm theo size (5 thùng 50, x thùng 70…) + list thùng."""
    code = _product_code(request)
    if not code:
        return web.json_response({"ok": False, "error": "Thiếu mã sản phẩm"}, status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            all_boxes = list_boxes(conn, product_code=code)
        finally:
            conn.close()
        return all_boxes
    all_boxes = await asyncio.to_thread(_run)
    # khả dụng phân bổ = thùng còn hiệu lực + còn lại > 0 (giữ quantity gốc + remaining)
    avail = [b for b in all_boxes if not b.get("disabled") and b.get("remaining", 0) > 0]
    # tồn = tổng CÒN LẠI → gộp theo remaining
    summary = summarize([{**b, "quantity": b["remaining"]} for b in avail])
    return web.json_response({
        "ok": True, "product_code": code, "boxes": avail, "all_boxes": all_boxes, **summary,
    })


# ─── xuất / thu thùng cho đơn ─────────────────────────────────────────────────
async def order_allocations_handler(request: web.Request):
    """Các phần thùng đã xuất cho đơn này (1 dòng = 1 phần thùng)."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            return list_order_allocations(conn, thread_id)
        finally:
            conn.close()
    allocs = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "allocations": allocs})


async def order_allocate_handler(request: web.Request):
    """Xuất kho cho đơn: picks=[{box_id, quantity?}] → ghi phần lấy (thùng KHÔNG tách).

    quantity thiếu = lấy hết phần còn lại của thùng.
    """
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    picks = body.get("picks")
    if not isinstance(picks, list) or not picks:
        box_ids = body.get("box_ids")
        if isinstance(box_ids, list) and box_ids:
            picks = [{"box_id": b, "quantity": None} for b in box_ids]
        else:
            return web.json_response({"ok": False, "error": "Chưa chọn thùng"}, status=400)
    actor = _web_actor(request, body)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            allocated = allocate_picks(conn, picks, thread_id, by=actor)
            return list_order_allocations(conn, thread_id), allocated
        finally:
            conn.close()
    allocs, allocated = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "allocated": allocated, "allocations": allocs})


async def order_release_handler(request: web.Request):
    """Thu hồi 1 phần thùng khỏi đơn (xoá allocation theo allocation_ids)."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    ids = body.get("allocation_ids")
    if not isinstance(ids, list) or not ids:
        return web.json_response({"ok": False, "error": "Chưa chọn phần thùng"}, status=400)
    try:
        ids = [int(x) for x in ids]
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "allocation_ids không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            _ensure(conn)
            released = []
            for aid in ids:
                a = get_allocation(conn, aid)
                if a and a.get("order_thread_id") == thread_id:
                    delete_allocation(conn, aid)
                    released.append(aid)
            return list_order_allocations(conn, thread_id), released
        finally:
            conn.close()
    allocs, released = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "released": released, "allocations": allocs})
