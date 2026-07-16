"""HTTP tra cứu sản phẩm cho webapp — autocomplete mã/tên SP khi nhập hoá đơn.

GET /api/products?search=&limit= → {ok, products:[{code, name}]}. Đọc từ
product_store (bảng products trong app.db, có cache). Lọc theo mã HOẶC tên
(không phân biệt hoa/thường, bỏ dấu qua vn_normalize). Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from order_db import _get_connection
from product_store.queries import get_all_products, get_product, upsert_product, delete_product, set_kiotviet_link, clear_kiotviet_link
from vn import vn_normalize

log = logging.getLogger("server")


def _actor(request: web.Request) -> str:
    u = request.get("web_user")
    return str((u or {}).get("display_name") or (u or {}).get("username") or "web") if isinstance(u, dict) else str(u or "web")


def _audit_product(action: str, product: dict | None, actor: str, **extra) -> None:
    """Ghi event lịch sử SP (scope='product', khoá theo id bất biến). No-op nếu thiếu id."""
    if not product or not product.get("id"):
        return
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked(f"audit.{action}", async_log_event(
        action, scope="product", thread_id=product.get("id"),
        actor_type="web_user", actor_id=actor, source=action,
        payload={"code": product.get("code"), **extra}))


async def product_create_handler(request: web.Request):
    """Tạo mã SP mới (danh mục local). Body {code, name?}. Trùng mã → trả mã sẵn có."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    code = (body.get("code") or "").upper().strip()
    if not code:
        return web.json_response({"ok": False, "error": "Thiếu mã SP"}, status=400)
    if code.isdigit():
        # mã toàn chữ số đụng key product_id trong bảng giá — cấm để phân biệt được
        return web.json_response({"ok": False, "error": "Mã SP không được toàn chữ số"}, status=400)
    name = (body.get("name") or "").strip()
    unit = (body.get("unit") or "").strip()

    def _run():
        conn = _get_connection()
        try:
            existed = get_product(conn, code) is not None
            upsert_product(conn, code, name=name or None, unit=unit or None)
            return get_product(conn, code), existed
        finally:
            conn.close()
    product, existed = await asyncio.to_thread(_run)
    from server_app.realtime import emit_inventory_changed
    emit_inventory_changed()
    if not existed:
        _audit_product("product.created", product, _actor(request), name=name)
    return web.json_response({"ok": True, "product": product, "existed": existed})


async def product_update_handler(request: web.Request):
    """Sửa SP (đơn vị / tên / ghi chú). Body {unit?, name?, note?}."""
    code = (request.match_info.get("code") or "").upper().strip()
    if not code:
        return web.json_response({"ok": False, "error": "Thiếu mã SP"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}

    def _run():
        conn = _get_connection()
        try:
            if not get_product(conn, code):
                return None
            upsert_product(conn, code,
                           name=body.get("name") if body.get("name") is not None else None,
                           note=body.get("note") if body.get("note") is not None else None,
                           unit=body.get("unit") if body.get("unit") is not None else None,
                           can_produce_directly=bool(body.get("can_produce_directly")) if body.get("can_produce_directly") is not None else None,
                           can_package=bool(body.get("can_package")) if body.get("can_package") is not None else None,
                           self_container=bool(body.get("self_container")) if body.get("self_container") is not None else None,
                           min_stock=body.get("min_stock") if body.get("min_stock") is not None else None,
                           can_sell=bool(body.get("can_sell")) if body.get("can_sell") is not None else None,
                           can_purchase=bool(body.get("can_purchase")) if body.get("can_purchase") is not None else None,
                           aux_required=bool(body.get("aux_required")) if body.get("aux_required") is not None else None)
            return get_product(conn, code)
        finally:
            conn.close()
    product = await asyncio.to_thread(_run)
    if not product:
        return web.json_response({"ok": False, "error": "Mã SP không tồn tại"}, status=404)
    from server_app.realtime import emit_inventory_changed
    emit_inventory_changed()
    _fields = ", ".join(k for k in ("name", "unit", "note", "can_produce_directly", "can_package", "can_sell", "can_purchase", "aux_required") if body.get(k) is not None)
    _audit_product("product.updated", product, _actor(request), fields=_fields)
    return web.json_response({"ok": True, "product": product})


async def product_kiotviet_search_handler(request: web.Request):
    """Tìm sản phẩm KiotViet để liên kết (từng cái). GET ?q= → [{id, code, full_name}]."""
    q = (request.query.get("q") or "").strip()
    if len(q) < 2:
        return web.json_response({"ok": True, "products": []})
    try:
        from integrations.kiotviet import search_products_kv
        products = await asyncio.to_thread(search_products_kv, q, 20)
    except Exception as e:  # noqa: BLE001
        log.error("Tìm SP KiotViet lỗi: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)
    return web.json_response({"ok": True, "products": products})


def _code(request):
    return (request.match_info.get("code") or "").upper().strip()


async def kiotviet_categories_handler(request: web.Request):
    """Danh sách nhóm hàng KiotViet (để chọn khi tạo SP mới). GET → [{id, name}]."""
    try:
        from integrations.kiotviet import list_categories_kv
        cats = await asyncio.to_thread(list_categories_kv, 100)
    except Exception as e:  # noqa: BLE001
        log.error("Lấy nhóm hàng KiotViet lỗi: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)
    return web.json_response({"ok": True, "categories": cats})


async def product_kv_create_handler(request: web.Request):
    """Tạo SP MỚI trên KiotViet từ mã local (dùng tên/đơn vị local) rồi LIÊN KẾT.
    CHỈ admin. Body {name?, unit?} ghi đè; giá cơ bản {base_price?}."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được tạo SP KiotViet"}, status=403)
    code = _code(request)
    if not code:
        return web.json_response({"ok": False, "error": "Thiếu mã SP"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}

    def _local():
        conn = _get_connection()
        try:
            return get_product(conn, code)
        finally:
            conn.close()
    local = await asyncio.to_thread(_local)
    if not local:
        return web.json_response({"ok": False, "error": "Mã SP chưa có trong danh mục"}, status=404)
    if local.get("kv_id"):
        return web.json_response({"ok": False, "error": "Mã đã liên kết KiotViet rồi"}, status=400)
    name = (body.get("name") or local.get("name") or code).strip()
    unit = (body.get("unit") or local.get("unit") or "").strip()
    try:
        category_id = int(body.get("category_id") or 0)
    except (TypeError, ValueError):
        category_id = 0
    if not category_id:
        return web.json_response({"ok": False, "error": "Chọn nhóm hàng KiotViet trước"}, status=400)
    try:
        base_price = float(body.get("base_price") or local.get("cost_price") or 0)
    except (TypeError, ValueError):
        base_price = 0
    # 1) tạo trên KiotViet
    try:
        from integrations.kiotviet import create_product_kv
        kv = await asyncio.to_thread(create_product_kv, code, name, category_id=category_id, unit=unit, base_price=base_price)
    except Exception as e:  # noqa: BLE001
        log.error("Tạo SP KiotViet lỗi: %s", e)
        return web.json_response({"ok": False, "error": f"KiotViet từ chối: {e}"}, status=502)
    if not kv.get("id"):
        return web.json_response({"ok": False, "error": "KiotViet không trả id SP"}, status=502)
    # 2) liên kết mã local ↔ KiotViet
    def _link():
        conn = _get_connection()
        try:
            return set_kiotviet_link(conn, code, int(kv["id"]), kv.get("full_name") or name)
        finally:
            conn.close()
    product = await asyncio.to_thread(_link)
    from server_app.realtime import emit_inventory_changed
    emit_inventory_changed()
    return web.json_response({"ok": True, "product": product, "kv": kv})


async def product_link_handler(request: web.Request):
    """Liên kết 1 mã SP với 1 sản phẩm KiotViet. Body {kv_id, kv_full_name?}."""
    code = _code(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    kv_id = body.get("kv_id")
    if not code or not kv_id:
        return web.json_response({"ok": False, "error": "Thiếu code / kv_id"}, status=400)

    def _run():
        conn = _get_connection()
        try:
            return set_kiotviet_link(conn, code, int(kv_id), body.get("kv_full_name") or "")
        finally:
            conn.close()
    product = await asyncio.to_thread(_run)
    if not product:
        return web.json_response({"ok": False, "error": "Không tìm thấy mã SP"}, status=404)
    from server_app.realtime import emit_inventory_changed
    emit_inventory_changed()
    _audit_product("product.linked", product, _actor(request), kv_id=int(kv_id), kv_name=body.get("kv_full_name") or "")
    return web.json_response({"ok": True, "product": product})


async def product_unlink_handler(request: web.Request):
    """Bỏ liên kết KiotViet của 1 mã SP."""
    code = _code(request)

    def _run():
        conn = _get_connection()
        try:
            return clear_kiotviet_link(conn, code)
        finally:
            conn.close()
    product = await asyncio.to_thread(_run)
    if not product:
        return web.json_response({"ok": False, "error": "Không tìm thấy mã SP"}, status=404)
    from server_app.realtime import emit_inventory_changed
    emit_inventory_changed()
    _audit_product("product.unlinked", product, _actor(request))
    return web.json_response({"ok": True, "product": product})


async def product_rename_handler(request: web.Request):
    """Đổi MÃ SP — CHỈ admin. Body {new_code}. Mọi liên kết nội bộ theo products.id
    tự đúng (kho/bảng giá/SX/đơn cũ hiện mã mới ngay); mã cũ thành alias (gõ vẫn
    nhận, link cũ redirect). SP có link KiotViet → đẩy mã mới sang KiotViet
    best-effort (fail chỉ cảnh báo — hoá đơn đã gửi bằng productId nên không vỡ)."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được đổi mã SP"}, status=403)
    code = _code(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    new_code = str(body.get("new_code") or "").strip()
    if not code or not new_code:
        return web.json_response({"ok": False, "error": "Thiếu mã mới"}, status=400)
    user = request.get("web_user")
    actor = str((user or {}).get("display_name") or (user or {}).get("username") or "web") if isinstance(user, dict) else str(user or "web")

    def _run():
        conn = _get_connection()
        try:
            from product_store import rename_product
            return rename_product(conn, code, new_code, by=actor)
        finally:
            conn.close()
    product, err = await asyncio.to_thread(_run)
    if err:
        return web.json_response({"ok": False, "error": err}, status=400)
    # KiotViet: đổi code bên đó cho khớp báo cáo — best-effort, không chặn
    kv_note = None
    if product.get("kv_id"):
        try:
            from integrations.kiotviet.products import update_product_code_kv
            await asyncio.to_thread(update_product_code_kv, product["kv_id"], product["code"])
            kv_note = "Đã đổi mã bên KiotViet"
        except Exception as e:  # noqa: BLE001
            log.warning("KiotViet rename push lỗi (%s → %s): %s", code, new_code, e)
            kv_note = f"KiotViet CHƯA đổi được mã ({e}) — hoá đơn vẫn tạo bình thường (gửi theo productId)"
    from server_app.realtime import (
        emit_inventory_changed, emit_orders_changed, emit_price_lists_changed, emit_productions_changed,
    )
    emit_inventory_changed()
    emit_price_lists_changed()
    emit_productions_changed()
    emit_orders_changed()
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.product_renamed", async_log_event(
        "product.renamed", scope="product", thread_id=product.get("id"),
        actor_type="web_user" if request.get("web_user") else "http_client",
        actor_id=actor, source="product.renamed",
        payload={"old_code": code, "new_code": product["code"], "kv": kv_note}))
    return web.json_response({"ok": True, "product": product, "kiotviet": kv_note})


async def product_delete_handler(request: web.Request):
    """Xoá 1 mã SP khỏi danh mục local — CHỈ admin. Không đụng đơn/thùng đã có."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá mã SP"}, status=403)
    code = _code(request)
    if not code:
        return web.json_response({"ok": False, "error": "Thiếu mã SP"}, status=400)

    def _run():
        conn = _get_connection()
        try:
            p = get_product(conn, code)
            if not p:
                return None, None
            pid = p.get("id")
            cu = str(code).upper()
            # (a) Còn thùng CÒN HÀNG (remaining > 0) → phải xử lý hết thùng trước.
            try:
                has_stock = conn.execute(
                    "SELECT 1 FROM inventory_boxes b WHERE (b.product_id = ? OR upper(b.product_code) = ?)"
                    " AND b.quantity - COALESCE("
                    "  (SELECT SUM(a.quantity) FROM box_allocations a WHERE a.box_id = b.id), 0) > 0"
                    " LIMIT 1", (pid, cu)).fetchone()
            except Exception:
                has_stock = None   # bảng chưa tồn tại (DB test) → không chặn
            if has_stock:
                return p, "stock"
            # (b) SP đang là NGUYÊN LIỆU trong công thức của SP khác → gỡ công thức trước.
            try:
                is_ingredient = conn.execute(
                    "SELECT 1 FROM product_recipes WHERE ingredient_id = ? LIMIT 1", (pid,)).fetchone()
            except Exception:
                is_ingredient = None
            if is_ingredient:
                return p, "ingredient"
            delete_product(conn, code)
            return p, None
        finally:
            conn.close()
    product, block = await asyncio.to_thread(_run)
    if not product:
        return web.json_response({"ok": False, "error": "Không tìm thấy mã SP"}, status=404)
    if block == "stock":
        return web.json_response({"ok": False, "error": "SP còn tồn kho — xử lý hết thùng trước khi xoá"}, status=400)
    if block == "ingredient":
        return web.json_response({"ok": False, "error": "SP đang là nguyên liệu trong công thức của SP khác — gỡ công thức trước"}, status=400)
    from server_app.realtime import emit_inventory_changed
    emit_inventory_changed()
    _audit_product("product.deleted", product, _actor(request))
    return web.json_response({"ok": True})


async def products_search_handler(request: web.Request):
    q = vn_normalize(request.query.get("search", "").strip())
    try:
        limit = max(1, min(50, int(request.query.get("limit", "20"))))
    except ValueError:
        limit = 20
    conn = _get_connection()
    products = get_all_products(conn)
    if q:
        products = [p for p in products
                    if q in vn_normalize(p["code"]) or q in vn_normalize(p.get("name") or "")]
    out = [{"id": p.get("id"), "code": p["code"], "name": p.get("name") or "",
            "can_produce_directly": bool(p.get("can_produce_directly")),
            "can_package": bool(p.get("can_package")),
            "can_sell": bool(p.get("can_sell", True)),
            "can_purchase": bool(p.get("can_purchase", True))} for p in products[:limit]]
    return web.json_response({"ok": True, "products": out})
