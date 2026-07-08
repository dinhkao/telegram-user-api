"""HTTP handlers khách hàng cho web app — GET /api/customers (tìm), GET /api/customers/{key}.

Đọc bảng `customers` (app.db) qua order_store.customers; trả gọn: tên, kh_id,
công nợ (debt), thread_id topic khách. Đăng ký ở server_app/app_factory.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from order_db import _get_connection, get_customer_by_key, search_customers
from order_store.customers import update_customer


def _summary(data: dict, firebase_key: str) -> dict:
    return {
        "key": firebase_key,
        "name": data.get("name") or data.get("ten") or firebase_key,
        "kh_id": data.get("kh_id"),
        "debt": data.get("debt"),
        "debt_updated_at": data.get("debt_updated_at"),
        "thread_id": data.get("thread_id"),
        "last_order_at": data.get("last_order_at"),
    }


async def customers_search_handler(request: web.Request):
    search = request.query.get("search", "").strip()
    sort = request.query.get("sort", "name")
    if sort not in ("name", "recent"):
        sort = "name"
    try:
        limit = max(1, min(50, int(request.query.get("limit", "20"))))
    except ValueError:
        limit = 20
    try:
        page = max(1, int(request.query.get("page", "1")))
    except ValueError:
        page = 1
    offset = (page - 1) * limit

    def _run():
        conn = _get_connection()
        try:
            return search_customers(conn, search, limit=limit, sort=sort, offset=offset)
        finally:
            conn.close()

    results, total = await asyncio.to_thread(_run)
    total_pages = max(1, -(-total // limit))
    return web.json_response({"ok": True, "customers": [_summary(c, c.get("_firebase_key", "")) for c in results],
                              "page": page, "total_pages": total_pages, "total": total})


async def customer_detail_handler(request: web.Request):
    key = request.match_info.get("key", "").strip()
    if not key:
        return web.json_response({"ok": False, "error": "thiếu key"}, status=400)

    def _run():
        conn = _get_connection()
        try:
            return get_customer_by_key(conn, key)
        finally:
            conn.close()

    data = await asyncio.to_thread(_run)
    if data is None:
        return web.json_response({"ok": False, "error": "không thấy khách hàng"}, status=404)
    return web.json_response({"ok": True, "customer": _detail(data, key)})


def _detail(data: dict, key: str) -> dict:
    """Payload chi tiết khách cho GET + sau update (1 chỗ, khỏi lệch)."""
    return {**_summary(data, key), "note": data.get("note") or data.get("ghi_chu") or "",
            "price_list": data.get("price_list"), "personal_price_list": data.get("personal_price_list"),
            "detectPatterns": data.get("detectPatterns") or data.get("patterns") or [],
            "default_tasks": data.get("default_tasks") or []}


async def customer_update_handler(request: web.Request):
    """Sửa khách từ web: bảng giá riêng (personal_price_list), pattern nhận diện
    (detectPatterns) và/hoặc việc mặc định (default_tasks — auto-thêm vào đơn khi
    gán khách). Chỉ ghi field có trong body. Ghi cả cục JSON qua update_customer
    (tự xoá cache pattern)."""
    key = request.match_info.get("key", "").strip()
    if not key:
        return web.json_response({"ok": False, "error": "thiếu key"}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "body phải là JSON"}, status=400)

    def _run():
        conn = _get_connection()
        try:
            data = get_customer_by_key(conn, key)
            if data is None:
                return None
            if "personal_price_list" in body and isinstance(body["personal_price_list"], dict):
                # {SP: giá int} — bỏ dòng trống / giá không hợp lệ
                clean = {}
                for sp, price in body["personal_price_list"].items():
                    sp = str(sp).strip()
                    try:
                        p = int(price)
                    except (TypeError, ValueError):
                        continue
                    if sp and p > 0:
                        clean[sp] = p
                data["personal_price_list"] = clean
            if "detectPatterns" in body and isinstance(body["detectPatterns"], list):
                data["detectPatterns"] = [str(p).strip() for p in body["detectPatterns"] if str(p).strip()]
            if "price_list" in body:
                # Gán bảng giá chung (id trong kv_store['bang_gia_moi']); "" / None = bỏ gán
                pl = body["price_list"]
                data["price_list"] = str(pl).strip() if pl not in (None, "") else None
            if "note" in body:
                # Ghi chú khách (dặn giao hàng…) — giờ sửa được từ web
                data["note"] = str(body["note"] or "").strip()
            if "default_tasks" in body and isinstance(body["default_tasks"], list):
                # Việc mặc định cho MỌI đơn của khách — strip, bỏ trùng (không phân
                # biệt hoa/thường), cắt 60 ký tự / việc, tối đa 15 việc
                seen, clean = set(), []
                for t in body["default_tasks"]:
                    s = str(t or "").strip()[:60]
                    if s and s.casefold() not in seen:
                        seen.add(s.casefold())
                        clean.append(s)
                data["default_tasks"] = clean[:15]
            ok, msg = update_customer(conn, key, data)
            return (data, ok, msg)
        finally:
            conn.close()

    res = await asyncio.to_thread(_run)
    if res is None:
        return web.json_response({"ok": False, "error": "không thấy khách hàng"}, status=404)
    data, ok, msg = res
    if not ok:
        return web.json_response({"ok": False, "error": msg}, status=500)
    from server_app.realtime import emit_customer_changed
    emit_customer_changed(key)
    return web.json_response({"ok": True, "customer": _detail(data, key)})


async def customer_orders_handler(request: web.Request):
    """Đơn của 1 khách — lọc CHÍNH XÁC theo khach_hang_id (= firebase_key khách)
    bằng json_extract, phân trang, dựng row compact như dashboard."""
    key = request.match_info.get("key", "").strip()
    if not key:
        return web.json_response({"ok": False, "error": "thiếu key"}, status=400)
    try:
        page = max(1, int(request.query.get("page", "1")))
    except ValueError:
        page = 1
    limit = 20
    offset = (page - 1) * limit

    def _run():
        from server_app.orders_api import _ROW_COLUMNS, _build_order_row, _attach_thumbs
        from server_app.orders_db import get_orders_conn
        conn = get_orders_conn()
        try:
            # CAST: khach_hang_id trong blob khi số khi chữ — so thẳng bỏ sót đơn lưu dạng số
            where = "WHERE CAST(json_extract(o.json, '$.khach_hang_id') AS TEXT) = ? AND o.deleted_at IS NULL"
            total = conn.execute(f"SELECT COUNT(*) FROM orders o {where}", (key,)).fetchone()[0]
            rows = conn.execute(
                f"SELECT {_ROW_COLUMNS} FROM orders o {where} ORDER BY o.thread_id DESC LIMIT ? OFFSET ?",
                (key, limit, offset),
            ).fetchall()
            orders = [_build_order_row(r) for r in rows]
            _attach_thumbs(conn, orders)
            return orders, total
        finally:
            conn.close()

    orders, total = await asyncio.to_thread(_run)
    total_pages = max(1, -(-total // limit))
    return web.json_response({"ok": True, "orders": orders, "page": page, "total_pages": total_pages, "total": total})


async def customer_refresh_debt_handler(request: web.Request):
    key = request.match_info.get("key", "").strip()
    if not key:
        return web.json_response({"ok": False, "error": "thiếu key"}, status=400)

    from server_app.debt_sync import refresh_single_debt
    try:
        data = await asyncio.to_thread(refresh_single_debt, key)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)
    if data is None:
        return web.json_response({"ok": False, "error": "không thấy khách hàng"}, status=404)
    from server_app.realtime import emit_customer_changed
    emit_customer_changed(key)
    return web.json_response({"ok": True, "customer": _summary(data, key)})
