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
    add_boxes,
    list_boxes,
    product_summary,
    get_box,
    allocate_boxes,
    release_boxes,
    summarize,
)
from production_store import get_slip, add_number
from server_app.production_routes import _web_actor
from utils.db import get_connection


def _conn():
    return get_connection()


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
    actor = _web_actor(request, body)

    def _run():
        conn = _conn()
        try:
            create_inventory_table(conn)
            migrate_inventory_table(conn)
            slip = get_slip(conn, thread_id)
            if not slip or not slip.get("sp_name"):
                return None, None
            code = str(slip["sp_name"]).strip().upper()
            created = add_boxes(conn, code, quantities, source_thread_id=thread_id, by=actor, note=note)
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


# ─── xem tồn kho ──────────────────────────────────────────────────────────────
async def inventory_list_handler(request: web.Request):
    """Dashboard kho: mỗi product tồn (in_stock) + số thùng đã xuất/đã giao."""
    def _run():
        conn = _conn()
        try:
            create_inventory_table(conn)
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
            create_inventory_table(conn)
            box = get_box(conn, box_id)
            slip = None
            if box and box.get("source_thread_id"):
                slip = get_slip(conn, box["source_thread_id"])
        finally:
            conn.close()
        return box, slip
    box, slip = await asyncio.to_thread(_run)
    if not box:
        return web.json_response({"ok": False, "error": "Không tìm thấy thùng"}, status=404)
    source = None
    if slip:
        source = {"thread_id": slip["thread_id"], "date": slip.get("date"), "sp_name": slip.get("sp_name")}
    return web.json_response({"ok": True, "box": box, "source_slip": source})


async def inventory_detail_handler(request: web.Request):
    """Tồn 1 product: tổng + nhóm theo size (5 thùng 50, x thùng 70…) + list thùng."""
    code = _product_code(request)
    if not code:
        return web.json_response({"ok": False, "error": "Thiếu mã sản phẩm"}, status=400)

    def _run():
        conn = _conn()
        try:
            create_inventory_table(conn)
            in_stock = list_boxes(conn, product_code=code, status="in_stock")
            all_boxes = list_boxes(conn, product_code=code)
        finally:
            conn.close()
        return in_stock, all_boxes
    in_stock, all_boxes = await asyncio.to_thread(_run)
    # boxes = in_stock (giữ tương thích ProductionBoxes/OrderStock); all_boxes = mọi status
    return web.json_response({
        "ok": True, "product_code": code, "boxes": in_stock, "all_boxes": all_boxes,
        **summarize(in_stock),
    })


# ─── xuất / thu thùng cho đơn ─────────────────────────────────────────────────
async def order_allocations_handler(request: web.Request):
    """Các thùng đã xuất cho đơn này (nhóm theo product)."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            create_inventory_table(conn)
            return list_boxes(conn, order_thread_id=thread_id)
        finally:
            conn.close()
    boxes = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "boxes": boxes})


async def order_allocate_handler(request: web.Request):
    """Xuất kho cho đơn: chọn box_ids in_stock → gán cho đơn này."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    box_ids = body.get("box_ids")
    if not isinstance(box_ids, list) or not box_ids:
        return web.json_response({"ok": False, "error": "Chưa chọn thùng"}, status=400)
    try:
        box_ids = [int(x) for x in box_ids]
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "box_ids không hợp lệ"}, status=400)
    actor = _web_actor(request, body)

    def _run():
        conn = _conn()
        try:
            create_inventory_table(conn)
            allocated = allocate_boxes(conn, box_ids, thread_id, by=actor)
            return list_boxes(conn, order_thread_id=thread_id), allocated
        finally:
            conn.close()
    boxes, allocated = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "allocated": allocated, "boxes": boxes})


async def order_release_handler(request: web.Request):
    """Thu hồi thùng đã xuất về kho (huỷ xuất)."""
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    box_ids = body.get("box_ids")
    if not isinstance(box_ids, list) or not box_ids:
        return web.json_response({"ok": False, "error": "Chưa chọn thùng"}, status=400)
    try:
        box_ids = [int(x) for x in box_ids]
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "box_ids không hợp lệ"}, status=400)

    def _run():
        conn = _conn()
        try:
            create_inventory_table(conn)
            released = release_boxes(conn, box_ids)
            return list_boxes(conn, order_thread_id=thread_id), released
        finally:
            conn.close()
    boxes, released = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "released": released, "boxes": boxes})
