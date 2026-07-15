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
        "nickname": data.get("nickname") or "",
        "kh_id": data.get("kh_id"),
        "debt": data.get("debt"),
        "debt_updated_at": data.get("debt_updated_at"),
        "thread_id": data.get("thread_id"),
        "last_order_at": data.get("last_order_at"),
    }


async def customers_search_handler(request: web.Request):
    search = request.query.get("search", "").strip()
    sort = request.query.get("sort", "name")
    if sort not in ("name", "recent", "debt"):
        sort = "name"
    owing = request.query.get("owing", "").strip() in ("1", "true")
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
        from order_db import customer_stats
        conn = _get_connection()
        try:
            res = search_customers(conn, search, limit=limit, sort=sort, offset=offset, owing=owing)
            # KPI dashboard khách — chỉ tính kèm ở trang 1 (đỡ quét lại mỗi trang cuộn)
            stats = customer_stats(conn) if page == 1 else None
            return res, stats
        finally:
            conn.close()

    (results, total), stats = await asyncio.to_thread(_run)
    total_pages = max(1, -(-total // limit))
    body = {"ok": True, "customers": [_summary(c, c.get("_firebase_key", "")) for c in results],
            "page": page, "total_pages": total_pages, "total": total}
    if stats is not None:
        body["stats"] = stats
    return web.json_response(body)


_DEBT_STALE_MS = 120_000   # chỉ refresh nền nếu nợ cũ hơn 2 phút (chặn spam KiotViet)


def _maybe_refresh_debt_bg(data: dict, key: str) -> None:
    """Kéo lại CÔNG NỢ khách từ KiotViet ở NỀN khi mở chi tiết — tự lành số nợ cũ
    (resync lỡ / KV trễ quá lâu). Fire-and-forget, KHÔNG chặn response; throttle
    theo debt_updated_at để không gọi KiotViet mỗi lần mở; chỉ khi đã liên kết KV.
    Vẫn lấy nợ TỪ KiotViet (không tính tay). Dùng chung schedule_debt_resync."""
    try:
        if not data.get("kh_id"):
            return
        import time as _t
        upd = float(data.get("debt_updated_at") or 0)
        if (_t.time() * 1000 - upd) < _DEBT_STALE_MS:
            return
        from server_app.debt_sync import schedule_debt_resync
        schedule_debt_resync(str(key), delay=0.0, followup_delay=None)
    except Exception:
        pass


async def customer_detail_handler(request: web.Request):
    key = request.match_info.get("key", "").strip()
    if not key:
        return web.json_response({"ok": False, "error": "thiếu key"}, status=400)

    def _run():
        conn = _get_connection()
        try:
            data = get_customer_by_key(conn, key)
            if data is not None:
                data = _with_display_prices(conn, data)
            return data
        finally:
            conn.close()

    data = await asyncio.to_thread(_run)
    if data is None:
        return web.json_response({"ok": False, "error": "không thấy khách hàng"}, status=404)
    _maybe_refresh_debt_bg(data, key)   # Fix B2: tự lành nợ cũ ở nền
    return web.json_response({"ok": True, "customer": _detail(data, key)})


def _with_display_prices(conn, data: dict) -> dict:
    """Bảng giá riêng lưu key = product_id → dịch về {MÃ HIỆN HÀNH: giá} cho UI."""
    raw = data.get("personal_price_list")
    if isinstance(raw, dict) and raw:
        from price_list_store.keys import effective_code_prices
        data = {**data, "personal_price_list": effective_code_prices(conn, raw, aliases=False)}
    return data


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
                # {SP: giá int} — bỏ dòng trống / giá không hợp lệ.
                # Lưu key theo product_id (đổi mã SP không vỡ giá riêng); mã lạ giữ legacy.
                from price_list_store.keys import to_pid_key
                clean = {}
                for sp, price in body["personal_price_list"].items():
                    sp = str(sp).strip()
                    try:
                        p = int(price)
                    except (TypeError, ValueError):
                        continue
                    if sp and p > 0:
                        clean[to_pid_key(conn, sp)] = p
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
            if "nickname" in body:
                # Tên gọi ngắn dùng ở các bề mặt chật (banner giao hàng…).
                data["nickname"] = str(body["nickname"] or "").strip()[:40]
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
            return (_with_display_prices(conn, data), ok, msg)
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


async def customer_kv_search_handler(request: web.Request):
    """GET /api/customers/kiotviet?q= — tìm khách TRÊN KiotViet (để liên kết)."""
    q = request.query.get("q", "").strip()
    if len(q) < 2:
        return web.json_response({"ok": True, "customers": []})
    from integrations.kiotviet.customers import search_customers_kv
    try:
        res = await asyncio.to_thread(search_customers_kv, q, 15)
    except Exception as e:  # noqa: BLE001
        return web.json_response({"ok": False, "error": str(e)}, status=502)
    return web.json_response({"ok": True, "customers": [
        {"id": c.get("id"), "code": c.get("code"), "name": c.get("name"),
         "debt": c.get("debt"), "phone": c.get("contactNumber")}
        for c in res if c.get("id")]})


def _save_customer_blob(conn, key: str, data: dict) -> None:
    import json as _json
    import time as _time
    now_ms = int(_time.time() * 1000)
    conn.execute("UPDATE customers SET json = ?, updated_at = ? WHERE firebase_key = ?",
                 (_json.dumps(data, ensure_ascii=False), now_ms, key))
    conn.commit()


async def customer_kv_link_handler(request: web.Request):
    """POST /api/customers/{key}/link-kiotviet {kv_id} — admin: gắn kh_id + kéo nợ ngay."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin được liên kết KiotViet"}, status=403)
    key = request.match_info.get("key", "").strip()
    try:
        body = await request.json()
        kv_id = int(body.get("kv_id"))
    except (TypeError, ValueError, Exception):  # noqa: BLE001
        return web.json_response({"ok": False, "error": "kv_id không hợp lệ"}, status=400)

    def _run():
        import time as _time
        from integrations.kiotviet.customers import get_customer_debt_kv
        det = get_customer_debt_kv(kv_id)   # ném lỗi nếu id không tồn tại
        conn = _get_connection()
        try:
            data = get_customer_by_key(conn, key)
            if data is None:
                return None
            data["kh_id"] = kv_id
            data["debt"] = det.get("debt")
            data["debt_updated_at"] = int(_time.time() * 1000)
            _save_customer_blob(conn, key, data)
            return data
        finally:
            conn.close()

    try:
        data = await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        return web.json_response({"ok": False, "error": f"KiotViet: {e}"}, status=502)
    if data is None:
        return web.json_response({"ok": False, "error": "không thấy khách hàng"}, status=404)
    from server_app.realtime import emit_customer_changed
    emit_customer_changed(key)
    return web.json_response({"ok": True, "customer": _detail(data, key)})


async def customer_kv_unlink_handler(request: web.Request):
    """POST /api/customers/{key}/unlink-kiotviet — admin: gỡ kh_id (giữ nợ đã lưu)."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin được bỏ liên kết"}, status=403)
    key = request.match_info.get("key", "").strip()

    def _run():
        conn = _get_connection()
        try:
            data = get_customer_by_key(conn, key)
            if data is None:
                return None
            data.pop("kh_id", None)
            _save_customer_blob(conn, key, data)
            return data
        finally:
            conn.close()

    data = await asyncio.to_thread(_run)
    if data is None:
        return web.json_response({"ok": False, "error": "không thấy khách hàng"}, status=404)
    from server_app.realtime import emit_customer_changed
    emit_customer_changed(key)
    return web.json_response({"ok": True, "customer": _detail(data, key)})


async def customer_delete_handler(request: web.Request):
    """DELETE /api/customers/{key} — admin XOÁ MỀM khách, CHỈ khi chưa liên kết
    KiotViet (kh_id) — khách đã liên kết phải bỏ liên kết trước (chống xoá nhầm
    khách thật đang theo dõi nợ)."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin được xoá khách"}, status=403)
    key = request.match_info.get("key", "").strip()

    def _run():
        import time as _time
        conn = _get_connection()
        try:
            data = get_customer_by_key(conn, key)
            if data is None:
                return "notfound"
            if data.get("kh_id"):
                return "linked"
            conn.execute("UPDATE customers SET deleted_at = ?, updated_at = ? WHERE firebase_key = ?",
                         (int(_time.time() * 1000), int(_time.time() * 1000), key))
            conn.commit()
            return "ok"
        finally:
            conn.close()

    res = await asyncio.to_thread(_run)
    if res == "notfound":
        return web.json_response({"ok": False, "error": "không thấy khách hàng"}, status=404)
    if res == "linked":
        return web.json_response({"ok": False, "error": "Khách đang liên kết KiotViet — bỏ liên kết trước rồi mới xoá"}, status=400)
    from server_app.realtime import emit_customer_changed
    emit_customer_changed(None)   # key=None = đổi CẤU TRÚC (xoá) → dashboard tải lại hẳn
    return web.json_response({"ok": True})
