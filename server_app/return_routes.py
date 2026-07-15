"""HTTP phiếu TRẢ HÀNG — /api/customers/{key}/returns (+ xoá).

POST (văn phòng): tạo HĐ KiotViet GIÁ ÂM (sl dương × giá âm — public API không có
POST /returns, số lượng âm bị chặn) → ghi return_slips + cập nhật nợ khách +
resync nền vá debt_after. DELETE (admin): xoá HĐ KV + xoá mềm phiếu.
Nối: return_store, integrations.kiotviet, server_app.debt_sync, server_app.realtime,
audit_log. Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from return_store import (add_return, clear_return_invoice, count_all_returns, get_return,
                          get_return_full, list_all_returns, list_returns,
                          set_return_invoice, soft_delete_return, update_return_items)
from utils.db import get_connection

log = logging.getLogger("return_routes")


def _actor(request: web.Request) -> str:
    u = request.get("web_user")
    if isinstance(u, dict):
        return str(u.get("display_name") or u.get("username") or "web")
    return str(u or "web")


def _normalize_items(conn, items: list[dict]) -> list[dict]:
    """Gắn sp_id + chuẩn hoá mã về hiện hành (nhận cả mã cũ) — như freeze của đơn."""
    from product_store import resolve_code
    out = []
    for it in items:
        it = dict(it)
        prod = resolve_code(conn, it.get("sp"))
        if prod:
            it["sp"] = prod["code"]
            it["sp_id"] = prod["id"]
        out.append(it)
    return out


def _items_display(conn, row: dict | None) -> dict | None:
    """Mã/tên item hiển thị = bản hiện hành (fallback snapshot)."""
    if row and row.get("items"):
        from order_store.display import resolve_invoice_display
        row = {**row, "items": resolve_invoice_display(row["items"], conn)}
    return row


def _parse_items(body: dict) -> tuple[list[dict], float] | None:
    """[{sp, sl, price}] (giá DƯƠNG) → (items chuẩn hoá, tổng). None = không hợp lệ."""
    items = []
    total = 0.0
    for it in body.get("items") or []:
        sp = str(it.get("sp") or "").strip().upper()
        try:
            sl = float(it.get("sl") or 0)
            price = float(it.get("price") or 0)
        except (TypeError, ValueError):
            return None
        if not sp or sl <= 0 or price <= 0:
            return None
        items.append({"sp": sp, "sl": sl, "price": price})
        total += sl * price
    return (items, total) if items and total > 0 else None


async def returns_all_handler(request: web.Request):
    """GET /api/returns?page= — dashboard trả hàng (mọi khách, 20/trang)."""
    try:
        page = max(1, int(request.query.get("page", "1")))
    except ValueError:
        page = 1
    limit = 20

    def _run():
        conn = get_connection()
        try:
            rows = [_items_display(conn, r) for r in list_all_returns(conn, limit=limit, offset=(page - 1) * limit)]
            return rows, count_all_returns(conn)
        finally:
            conn.close()
    rows, total = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "returns": rows, "page": page,
                              "total": total, "total_pages": max(1, (total + limit - 1) // limit)})


async def return_detail_handler(request: web.Request):
    """GET /api/returns/{id} — chi tiết 1 phiếu trả."""
    try:
        rid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    def _get():
        conn = get_connection()
        try:
            return _items_display(conn, get_return_full(conn, rid))
        finally:
            conn.close()
    row = await asyncio.to_thread(_get)
    if not row:
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu trả"}, status=404)
    return web.json_response({"ok": True, "return": row})


async def return_handle_goods_handler(request: web.Request):
    """POST /api/returns/{id}/handle-goods (văn phòng) — xử lý HÀNG khách trả về.

    body {dispositions: [{sp, quantity, action, box_id?, place_id?, unit_id?}]}
      action = 'restock_existing' (nhập vào thùng có sẵn: +quantity vào thùng)
             | 'restock_new'      (tạo thùng mới cho hàng trả)
             | 'dispose'          (gom vào 1 phiếu XUẤT HỦY box-less — không trừ tồn)
             | 'skip'.
    Idempotent-guard: phiếu đã xử lý → 409 (tránh nhập/hủy 2 lần)."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được xử lý hàng trả"}, status=403)
    try:
        rid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    dispositions = body.get("dispositions") if isinstance(body.get("dispositions"), list) else []
    actor = _actor(request)

    def _run():
        from server_app.return_goods import apply_goods_dispositions
        conn = get_connection()
        try:
            extra, err = apply_goods_dispositions(conn, rid, dispositions, actor=actor)
            if err:
                return None, err, None
            updated = _items_display(conn, get_return_full(conn, rid))
            return updated, None, extra
        finally:
            conn.close()

    row, err, extra = await asyncio.to_thread(_run)
    if err == "not_found":
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu trả"}, status=404)
    if err == "already":
        return web.json_response({"ok": False, "error": "Hàng trả của phiếu này đã xử lý rồi"}, status=409)

    from server_app.realtime import (emit_return_changed, emit_inventory_changed,
                                      emit_box_changed, emit_disposal_changed, emit_customer_changed)
    emit_return_changed(rid)
    if extra["customer_key"]:
        emit_customer_changed(extra["customer_key"])
    result = extra["result"]
    if result["restocked_existing"] or result["restocked_new"]:
        emit_inventory_changed()
        for bid in extra["touched_boxes"]:
            emit_box_changed(bid)
    if extra["disposal"]:
        emit_disposal_changed(extra["disposal"]["id"])
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    at = "web_user" if request.get("web_user") else "http_client"
    spawn_tracked("audit.return_goods", async_log_event(
        "return.goods_handled", scope="return", thread_id=rid,
        actor_type=at, actor_id=actor, source="return.goods_handled", payload={"result": result}))
    if extra["disposal"]:
        d = extra["disposal"]
        spawn_tracked("audit.disposal_created", async_log_event(
            "disposal.created", scope="disposal", thread_id=d["id"],
            actor_type=at, actor_id=actor, source="return.goods_handled",
            payload={"reason": d["reason"], "items": d["items"],
                     "total_quantity": d["total_quantity"], "source_return_id": rid}))
    return web.json_response({"ok": True, "return": row, "result": result})


async def returns_list_handler(request: web.Request):
    key = request.match_info.get("key", "").strip()
    if not key:
        return web.json_response({"ok": False, "error": "thiếu key"}, status=400)
    def _list():
        conn = get_connection()
        try:
            return [_items_display(conn, r) for r in list_returns(conn, key)]
        finally:
            conn.close()
    rows = await asyncio.to_thread(_list)
    return web.json_response({"ok": True, "returns": rows})


async def returns_create_handler(request: web.Request):
    """Body {items: [{sp, sl, price}], note?, thread_id?} — giá DƯƠNG (tiền trả)."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được tạo phiếu trả hàng"}, status=403)
    key = request.match_info.get("key", "").strip()
    try:
        body = await request.json()
    except Exception:
        body = {}
    parsed = _parse_items(body)
    if not key or not parsed:
        return web.json_response({"ok": False, "error": "Danh sách hàng trả không hợp lệ (cần sp + sl>0 + giá>0)"}, status=400)
    items, total = parsed
    note = str(body.get("note") or "").strip()
    thread_id = body.get("thread_id")
    actor = _actor(request)

    # NHÁP: chỉ ghi sổ app, CHƯA đụng KiotViet — bấm 'Tạo HĐ KiotViet' ở trang
    # chi tiết mới trừ nợ (giống đơn: tạo đơn trước, bán HĐ sau)
    def _save():
        conn = get_connection()
        try:
            return add_return(conn, key, _normalize_items(conn, items), total, note=note, thread_id=thread_id, by=actor)
        finally:
            conn.close()
    row = await asyncio.to_thread(_save)

    from server_app.realtime import emit_customer_changed, emit_return_changed
    emit_customer_changed(key)
    emit_return_changed(row["id"])
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.return_created", async_log_event(
        "return.created", scope="return", thread_id=row["id"],
        actor_type="web_user" if request.get("web_user") else "http_client",
        actor_id=actor, source="return.created",
        payload={"customer_key": key, "total": total}))
    return web.json_response({"ok": True, "return": row})


async def return_update_handler(request: web.Request):
    """POST /api/returns/{id}/update (văn phòng) — sửa hàng trả/ghi chú, CHỈ khi
    còn NHÁP (đã gắn HĐ KV thì khoá — xoá HĐ mới sửa được)."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được sửa phiếu trả"}, status=403)
    try:
        rid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    parsed = _parse_items(body)
    if not parsed:
        return web.json_response({"ok": False, "error": "Danh sách hàng trả không hợp lệ"}, status=400)
    items, total = parsed
    note = str(body.get("note") or "").strip()
    row = await asyncio.to_thread(lambda: get_return(get_connection(), rid))
    if not row or row.get("deleted_at"):
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu trả"}, status=404)
    if row.get("kv_invoice_id"):
        return web.json_response({"ok": False, "error": "Phiếu đã có HĐ KiotViet — xoá HĐ mới sửa được", "locked": True}, status=400)
    # Đã XỬ LÝ HÀNG (nhập kho / xuất hủy) rồi → items đã khớp hàng thực xử lý; sửa
    # items lúc này làm lệch kho↔nợ mà không hoàn tác được → cấm sửa.
    if row.get("goods_handled_at"):
        return web.json_response({"ok": False, "error": "Phiếu đã xử lý hàng (nhập/hủy) — không sửa được nữa", "locked": True}, status=400)
    def _upd():
        conn = get_connection()
        try:
            update_return_items(conn, rid, _normalize_items(conn, items), total, note)
        finally:
            conn.close()
    await asyncio.to_thread(_upd)
    from server_app.realtime import emit_customer_changed, emit_return_changed
    emit_return_changed(rid)
    emit_customer_changed(str(row["customer_key"]))
    return web.json_response({"ok": True})


async def return_invoice_handler(request: web.Request):
    """POST /api/returns/{id}/invoice (văn phòng) — tạo HĐ KiotViet GIÁ ÂM cho
    phiếu nháp → trừ công nợ khách. Idempotent: đã có HĐ thì trả lỗi."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được tạo HĐ trả hàng"}, status=403)
    try:
        rid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    row = await asyncio.to_thread(lambda: get_return(get_connection(), rid))
    if not row or row.get("deleted_at"):
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu trả"}, status=404)
    if row.get("kv_invoice_id"):
        return web.json_response({"ok": False, "error": "Phiếu đã có HĐ KiotViet rồi"}, status=400)
    key = str(row["customer_key"])

    def _kh_id():
        conn = get_connection()
        try:
            r = conn.execute(
                "SELECT json_extract(json,'$.kh_id') FROM customers WHERE firebase_key = ? AND deleted_at IS NULL",
                (key,)).fetchone()
            return r[0] if r else None
        finally:
            conn.close()
    kh_id = await asyncio.to_thread(_kh_id)
    if not kh_id:
        return web.json_response({"ok": False, "error": "Khách chưa liên kết KiotViet"}, status=400)

    from integrations.kiotviet.customers import get_customer_debt_kv
    from integrations.kiotviet.invoices import create_kiotviet_invoice
    items = row.get("items") or []
    total = float(row.get("total") or 0)
    kv_items = [{"sp": it["sp"], "sl": int(it["sl"]), "price": -int(it["price"])} for it in items]
    try:
        debt_before = (await asyncio.to_thread(get_customer_debt_kv, kh_id)).get("debt")
    except Exception:
        debt_before = None
    def _kv_map():
        from product_store import kv_ids_for_items
        conn = get_connection()
        try:
            return kv_ids_for_items(conn, kv_items)
        finally:
            conn.close()
    kv_map = await asyncio.to_thread(_kv_map)
    try:
        inv = await asyncio.to_thread(
            create_kiotviet_invoice, customer_id=int(kh_id), invoice_items=kv_items, kv_ids=kv_map)
    except Exception as e:
        log.error("return invoice failed id=%s: %s", rid, e)
        return web.json_response({"ok": False, "error": f"Lỗi tạo HĐ trả hàng KiotViet: {e}"}, status=502)
    debt_after = (float(debt_before) - total) if debt_before is not None else None

    def _apply():
        conn = get_connection()
        try:
            set_return_invoice(conn, rid, inv.get("id"), inv.get("code"), debt_before, debt_after)
            if debt_after is not None:
                from order_db import update_customer_debt
                update_customer_debt(conn, key, debt_after)
        finally:
            conn.close()
    await asyncio.to_thread(_apply)

    from server_app.debt_sync import schedule_debt_resync
    schedule_debt_resync(key, return_id=rid)
    from server_app.realtime import emit_customer_changed, emit_return_changed
    emit_return_changed(rid)
    emit_customer_changed(key)
    actor = _actor(request)
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.return_invoiced", async_log_event(
        "return.invoiced", scope="return", thread_id=rid,
        actor_type="web_user" if request.get("web_user") else "http_client",
        actor_id=actor, source="return.invoiced",
        payload={"customer_key": key, "total": total, "kv_code": inv.get("code")}))
    return web.json_response({"ok": True, "kv_code": inv.get("code"), "kv_id": inv.get("id"),
                              "debt_before": debt_before, "debt_after": debt_after})


async def return_invoice_delete_handler(request: web.Request):
    """POST /api/returns/{id}/delete-invoice (CHỈ admin) — xoá HĐ KiotViet giá âm,
    công nợ khách CỘNG lại, phiếu về NHÁP (sửa/xoá được). Quy trình y như đơn."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá HĐ KiotViet"}, status=403)
    try:
        rid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    row = await asyncio.to_thread(lambda: get_return(get_connection(), rid))
    if not row or row.get("deleted_at"):
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu trả"}, status=404)
    if not row.get("kv_invoice_id"):
        return web.json_response({"ok": False, "error": "Phiếu chưa có HĐ KiotViet"}, status=400)
    from integrations.kiotviet.invoices import delete_invoice_kv
    try:
        await asyncio.to_thread(delete_invoice_kv, int(row["kv_invoice_id"]))
    except Exception as e:
        log.error("delete return invoice failed id=%s: %s", rid, e)
        return web.json_response({"ok": False, "error": f"Lỗi xoá HĐ KiotViet: {e}"}, status=502)
    kv_code = row.get("kv_invoice_code")
    await asyncio.to_thread(lambda: clear_return_invoice(get_connection(), rid))
    key = str(row["customer_key"])
    from server_app.debt_sync import schedule_debt_resync
    schedule_debt_resync(key)
    from server_app.realtime import emit_customer_changed, emit_return_changed
    emit_return_changed(rid)
    emit_customer_changed(key)
    actor = _actor(request)
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.return_invoice_deleted", async_log_event(
        "return.invoice_deleted", scope="return", thread_id=rid,
        actor_type="web_user", actor_id=actor, source="return.invoice_deleted",
        payload={"customer_key": key, "kv_code": kv_code}))
    return web.json_response({"ok": True})


async def returns_delete_handler(request: web.Request):
    """Xoá phiếu trả (CHỈ admin): xoá HĐ KV âm + xoá mềm row + resync nợ."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá phiếu trả hàng"}, status=403)
    try:
        rid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    row = await asyncio.to_thread(lambda: get_return(get_connection(), rid))
    if not row or row.get("deleted_at"):
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu trả"}, status=404)
    # QUY TRÌNH như đơn: còn HĐ KiotViet → phải xoá HĐ trước rồi mới xoá phiếu
    if row.get("kv_invoice_id"):
        return web.json_response(
            {"ok": False, "error": "Phiếu còn HĐ KiotViet — xoá HĐ trước rồi mới xoá phiếu", "locked": True},
            status=400)
    actor = _actor(request)
    await asyncio.to_thread(lambda: soft_delete_return(get_connection(), rid, by=actor))
    from server_app.debt_sync import schedule_debt_resync
    schedule_debt_resync(str(row["customer_key"]))
    from server_app.realtime import emit_customer_changed
    emit_customer_changed(str(row["customer_key"]))
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    from server_app.realtime import emit_return_changed
    emit_return_changed(rid)
    spawn_tracked("audit.return_deleted", async_log_event(
        "return.deleted", scope="return", thread_id=rid,
        actor_type="web_user", actor_id=actor, source="return.deleted",
        payload={"customer_key": row["customer_key"], "kv_code": row.get("kv_invoice_code")}))
    return web.json_response({"ok": True})
