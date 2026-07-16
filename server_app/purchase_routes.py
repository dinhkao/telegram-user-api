"""HTTP phiếu NHẬP HÀNG — /api/purchases (100% local, không KiotViet).

GET list phân trang (dashboard) / POST tạo (văn phòng, body {supplier_id, items,
note?}) / GET {id} / POST {id}/update sửa (văn phòng) / POST {id}/delete xoá mềm
(admin) / POST {id}/pay TRẢ TIỀN NCC TỪ KÉT của mình (đăng nhập; admin: két bất
kỳ; chặn quá số dư két + quá phần còn nợ, serialize qua cashbox _transfer_lock)
/ POST {id}/payments/{pid}/delete gỡ 1 lần trả (admin). Items dùng chung bảng
SẢN PHẨM: mã resolve qua product_store (nhận cả mã cũ) → gắn sp_id; hiển thị
mã/tên bản hiện hành như đơn.
Nối: purchase_store, supplier_store, product_store, cashbox_store,
server_app.cashbox_routes (_transfer_lock, _norm_box), server_app.realtime,
audit_log. Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from purchase_store import (add_purchase, count_all_purchases, get_purchase,
                            get_purchase_full, list_all_purchases,
                            soft_delete_purchase, update_purchase_items)
from utils.db import get_connection

log = logging.getLogger("purchase_routes")


def _actor(request: web.Request) -> str:
    u = request.get("web_user")
    if isinstance(u, dict):
        return str(u.get("display_name") or u.get("username") or "web")
    return str(u or "web")


def _get_purchase_closed(pid: int) -> dict | None:
    """get_purchase với connection đóng tử tế (tránh leak mỗi request)."""
    conn = get_connection()
    try:
        return get_purchase(conn, pid)
    finally:
        conn.close()


_names_cache: dict = {"t": 0.0, "names": {}}


def _user_names() -> dict:
    """username → display_name, cache 30s (khỏi mở DB mỗi row khi enrich payments)."""
    import time as _t
    if _t.time() - _names_cache["t"] > 30:
        from user_store import list_users
        _names_cache["names"] = {u["username"]: (u.get("display_name") or u["username"])
                                 for u in list_users()}
        _names_cache["t"] = _t.time()
    return _names_cache["names"]


def _normalize_items(conn, items: list[dict]) -> list[dict]:
    """Gắn sp_id + chuẩn hoá mã về hiện hành (nhận cả mã cũ) — như phiếu trả/đơn.
    Mã không resolve được vẫn giữ nguyên (NCC có thể có hàng ngoài danh mục)."""
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
    """Mã/tên item hiển thị = bản hiện hành (fallback snapshot) + ĐƠN VỊ GỐC của SP
    (base_unit — bảng hàng nhập hiện đơn vị cả khi không chọn đơn vị quy đổi) + tên
    người/két cho payments ('tri'/'user:tri' → 'Trí'/'Két Trí' — nhất quán trang Két)."""
    if row and row.get("items"):
        from order_store.display import resolve_invoice_display
        items = resolve_invoice_display(row["items"], conn)
        try:
            from product_store.queries import get_all_products
            prods = get_all_products(conn)
            by_id = {p.get("id"): p for p in prods}
            by_code = {str(p.get("code") or "").upper(): p for p in prods}
            items = [dict(it) for it in items]
            for it in items:
                p = by_id.get(it.get("sp_id")) or by_code.get(str(it.get("sp") or "").upper())
                if p:
                    it["base_unit"] = p.get("unit") or "cây"
        except Exception:  # noqa: BLE001 — enrich hỏng vẫn trả items thô
            pass
        row = {**row, "items": items}
    if row and row.get("payments"):
        try:
            from cashbox_store.identity import BOX_NAMES, box_display
            names = _user_names()
            pays = []
            for p in row["payments"]:
                box = str(p.get("box") or "")
                box_name = BOX_NAMES.get(box) or (
                    f"Két {names.get(box[5:], box[5:])}" if box.startswith("user:") else box_display(box))
                pays.append({**p, "by_name": names.get(str(p.get("by")), str(p.get("by") or "")),
                             "box_name": box_name})
            row = {**row, "payments": pays}
        except Exception:  # noqa: BLE001 — enrich hỏng vẫn trả payments thô
            pass
    return row


def _parse_items(body: dict) -> tuple[list[dict], float] | None:
    """[{sp, sl, price, unit?, unit_factor?}] → (items, tổng). Giá ≥ 0 (hàng tặng
    kèm giá 0 hợp lệ). unit/unit_factor = ĐƠN VỊ NHẬP đã chọn (snapshot từ
    product_units): sl + giá tính theo đơn vị đó, 1 unit = unit_factor đơn vị gốc
    (quy về gốc khi nhập kho). None = không hợp lệ."""
    items = []
    total = 0.0
    for it in body.get("items") or []:
        sp = str(it.get("sp") or "").strip().upper()
        try:
            sl = float(it.get("sl") or 0)
            price = float(it.get("price") or 0)
        except (TypeError, ValueError):
            return None
        if not sp or sl <= 0 or price < 0:
            return None
        row = {"sp": sp, "sl": sl, "price": price}
        unit = str(it.get("unit") or "").strip()[:40]
        try:
            factor = float(it.get("unit_factor") or 0)
        except (TypeError, ValueError):
            factor = 0.0
        if unit and factor > 0:
            row["unit"] = unit
            row["unit_factor"] = factor
        items.append(row)
        total += sl * price
    return (items, total) if items else None


async def purchases_all_handler(request: web.Request):
    """GET /api/purchases?page= — dashboard nhập hàng (mọi NCC, 20/trang)."""
    try:
        page = max(1, int(request.query.get("page", "1")))
    except ValueError:
        page = 1
    limit = 20

    def _run():
        conn = get_connection()
        try:
            rows = [_items_display(conn, r) for r in list_all_purchases(conn, limit=limit, offset=(page - 1) * limit)]
            total = count_all_purchases(conn)
            # Gắn trạng thái nhập dở cho dashboard — chỉ tra phiếu ĐANG MỞ (phiếu
            # đã chốt vẫn còn thùng/allocation purchase_in trong kho → tra sẽ
            # dính True oan; badge chỉ có nghĩa khi chưa chốt)
            from purchase_store import batch_draft_status
            pids = [r["id"] for r in rows if r and not r.get("goods_handled_at")]
            draft_map = batch_draft_status(conn, pids)
            for r in rows:
                if r:
                    r["has_draft"] = draft_map.get(r["id"], False)
            return rows, total
        finally:
            conn.close()
    rows, total = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "purchases": rows, "page": page,
                              "total": total, "total_pages": max(1, (total + limit - 1) // limit)})


async def purchase_detail_handler(request: web.Request):
    """GET /api/purchases/{id} — chi tiết 1 phiếu nhập (kèm tên NCC)."""
    try:
        pid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    def _get():
        from server_app.purchase_goods_view import attach_purchase_boxes, mark_deleted_boxes
        conn = get_connection()
        try:
            # gắn box_deleted cho thùng đã bị admin xoá — UI hiện 'đã xoá' thay link chết
            # + boxes (info đầy đủ) → trang chi tiết vẽ Ô THÙNG như trong đơn hàng
            return attach_purchase_boxes(
                conn, mark_deleted_boxes(conn, _items_display(conn, get_purchase_full(conn, pid))))
        finally:
            conn.close()
    row = await asyncio.to_thread(_get)
    if not row:
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu nhập"}, status=404)
    return web.json_response({"ok": True, "purchase": row})


async def purchase_create_handler(request: web.Request):
    """POST /api/purchases (văn phòng) — body {supplier_id, items: [{sp, sl, price}], note?}."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được tạo phiếu nhập"}, status=403)
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        supplier_id = int(body.get("supplier_id") or 0)
    except (TypeError, ValueError):
        supplier_id = 0
    parsed = _parse_items(body)
    if not supplier_id or not parsed:
        return web.json_response(
            {"ok": False, "error": "Cần nhà cung cấp + danh sách hàng nhập (sp + sl>0 + giá≥0)"}, status=400)
    items, total = parsed
    note = str(body.get("note") or "").strip()
    actor = _actor(request)

    def _save():
        conn = get_connection()
        try:
            from supplier_store import get_supplier
            sup = get_supplier(conn, supplier_id)
            if not sup or sup.get("deleted_at"):
                return None
            return add_purchase(conn, supplier_id, _normalize_items(conn, items), total, note=note, by=actor)
        finally:
            conn.close()
    row = await asyncio.to_thread(_save)
    if not row:
        return web.json_response({"ok": False, "error": "Nhà cung cấp không tồn tại"}, status=400)

    from server_app.realtime import emit_purchase_changed, emit_supplier_changed
    emit_purchase_changed(row["id"])
    emit_supplier_changed(supplier_id)   # thống kê NCC (số phiếu/tổng tiền) đổi
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.purchase_created", async_log_event(
        "purchase.created", scope="purchase", thread_id=row["id"],
        actor_type="web_user" if request.get("web_user") else "http_client",
        actor_id=actor, source="purchase.created",
        payload={"supplier_id": supplier_id, "total": total}))
    return web.json_response({"ok": True, "purchase": row})


async def purchase_update_handler(request: web.Request):
    """POST /api/purchases/{id}/update (văn phòng) — sửa hàng nhập/ghi chú/NCC."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được sửa phiếu nhập"}, status=403)
    try:
        pid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    parsed = _parse_items(body)
    if not parsed:
        return web.json_response({"ok": False, "error": "Danh sách hàng nhập không hợp lệ"}, status=400)
    items, total = parsed
    note = str(body.get("note") or "").strip()
    new_supplier = body.get("supplier_id")
    row = await asyncio.to_thread(_get_purchase_closed, pid)
    if not row or row.get("deleted_at"):
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu nhập"}, status=404)
    if row.get("goods_handled_at"):
        # hàng đã vào thùng theo phiếu này — sửa items sau đó sẽ lệch kho
        return web.json_response(
            {"ok": False, "error": "Phiếu đã nhập kho — không sửa hàng được nữa"}, status=400)

    def _upd():
        conn = get_connection()
        try:
            sid = None
            if new_supplier is not None:
                from supplier_store import get_supplier
                sup = get_supplier(conn, int(new_supplier))
                if not sup or sup.get("deleted_at"):
                    return False, "Nhà cung cấp không tồn tại"
                sid = int(new_supplier)
            return update_purchase_items(conn, pid, _normalize_items(conn, items), total, note, supplier_id=sid)
        finally:
            conn.close()
    ok, upd_err = await asyncio.to_thread(_upd)
    if not ok:
        return web.json_response({"ok": False, "error": upd_err}, status=400)
    from server_app.realtime import emit_purchase_changed, emit_supplier_changed
    emit_purchase_changed(pid)
    emit_supplier_changed(int(row["supplier_id"]))
    if new_supplier is not None and int(new_supplier) != int(row["supplier_id"]):
        emit_supplier_changed(int(new_supplier))
    return web.json_response({"ok": True})


async def purchase_pay_handler(request: web.Request):
    """POST /api/purchases/{id}/pay {amount, box?} — trả tiền NCC từ két.
    Mặc định két của CHÍNH người gọi; chọn két khác = admin."""
    user = request.get("web_user")
    if not user:
        return web.json_response({"ok": False, "error": "Cần đăng nhập để trả tiền từ két"}, status=401)
    try:
        pid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        amount = int(round(float(body.get("amount") or 0)))
    except (TypeError, ValueError, OverflowError):
        amount = 0
    if amount <= 0:
        return web.json_response({"ok": False, "error": "Số tiền phải > 0"}, status=400)
    from server_app.cashbox_routes import _norm_box, _transfer_lock
    own = f"user:{str(user).lower()}"
    box = _norm_box(str(body.get("box") or own))
    if not box:
        return web.json_response({"ok": False, "error": "Két không hợp lệ"}, status=400)
    if box != own:
        from server_app.order_api_common import is_admin_request
        if not await is_admin_request(request):
            return web.json_response({"ok": False, "error": "Chỉ được trả từ két của mình"}, status=403)

    import time as _time
    import cashbox_store
    from cashbox_store.service import cashbox_balance
    from purchase_store import add_purchase_payment

    def _pay():
        conn = get_connection()
        try:
            return add_purchase_payment(conn, pid, amount, box, str(user))
        finally:
            conn.close()

    async with _transfer_lock:   # check số dư két + ghi payment = 1 khối
        balance = await asyncio.to_thread(cashbox_balance, box, _time.time())
        if amount > balance:
            return web.json_response(
                {"ok": False, "error": f"Két chỉ còn {balance:,}đ — không đủ {amount:,}đ".replace(",", ".")},
                status=400)
        rec, err = await asyncio.to_thread(_pay)
        if not rec:
            status = 404 if "Không tìm thấy" in err else 400
            return web.json_response({"ok": False, "error": err}, status=status)
        cashbox_store.invalidate_cache()

    row = await asyncio.to_thread(_get_purchase_closed, pid)
    from server_app.realtime import emit_cashbox_changed, emit_purchase_changed
    emit_purchase_changed(pid)
    emit_cashbox_changed()
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.purchase_paid", async_log_event(
        "purchase.paid", scope="purchase", thread_id=pid,
        actor_type="web_user", actor_id=str(user), source="purchase.paid",
        payload={"amount": amount, "box": box, "payment_id": rec["id"],
                 "supplier_id": (row or {}).get("supplier_id")}))
    return web.json_response({"ok": True, "payment": rec, "purchase": row})


async def purchase_payment_delete_handler(request: web.Request):
    """POST /api/purchases/{id}/payments/{pid}/delete (CHỈ admin) — gỡ 1 lần trả,
    tiền tự tính lại về két (derive)."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được gỡ lần trả tiền"}, status=403)
    try:
        pid = int(request.match_info.get("id", ""))
        pmid = int(request.match_info.get("pid", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)

    from purchase_store import delete_purchase_payment

    def _del():
        conn = get_connection()
        try:
            return delete_purchase_payment(conn, pid, pmid)
        finally:
            conn.close()
    removed = await asyncio.to_thread(_del)
    if not removed:
        return web.json_response({"ok": False, "error": "Không tìm thấy lần trả tiền"}, status=404)
    import cashbox_store
    cashbox_store.invalidate_cache()
    from server_app.realtime import emit_cashbox_changed, emit_purchase_changed
    emit_purchase_changed(pid)
    emit_cashbox_changed()
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.purchase_payment_deleted", async_log_event(
        "purchase.payment_deleted", scope="purchase", thread_id=pid,
        actor_type="web_user", actor_id=_actor(request), source="purchase.payment_deleted",
        payload={"amount": removed.get("amount"), "box": removed.get("box")}))
    return web.json_response({"ok": True})


async def purchase_delete_handler(request: web.Request):
    """POST /api/purchases/{id}/delete (CHỈ admin) — xoá mềm phiếu nhập."""
    from server_app.order_api_common import is_admin_request
    if not await is_admin_request(request):
        return web.json_response({"ok": False, "error": "Chỉ admin mới được xoá phiếu nhập"}, status=403)
    try:
        pid = int(request.match_info.get("id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    row = await asyncio.to_thread(_get_purchase_closed, pid)
    if not row or row.get("deleted_at"):
        return web.json_response({"ok": False, "error": "Không tìm thấy phiếu nhập"}, status=404)
    if row.get("payments"):
        # xoá phiếu = payments biến khỏi derive → tiền "tự quay về" két người trả
        # trong khi tiền mặt đã đưa NCC. Bắt gỡ từng lần trả (đường admin có audit).
        return web.json_response(
            {"ok": False, "error": f"Phiếu còn {len(row['payments'])} lần trả tiền — gỡ các lần trả trước khi xoá phiếu"},
            status=400)
    if row.get("goods_handled_at"):
        # hàng đã vào thùng kho — xoá phiếu sẽ mồ côi thùng/allocation nguồn
        return web.json_response(
            {"ok": False, "error": "Phiếu đã nhập kho — không xoá được (hàng đã vào thùng)"}, status=400)
    actor = _actor(request)

    def _del_slip():
        conn = get_connection()
        try:
            return soft_delete_purchase(conn, pid, by=actor)
        finally:
            conn.close()
    ok, del_err = await asyncio.to_thread(_del_slip)
    if not ok:
        # kho còn thùng tạo từ phiếu (kể cả sau hủy chốt) — xoá phiếu sẽ mồ côi thùng
        return web.json_response({"ok": False, "error": del_err}, status=400)
    from server_app.realtime import emit_purchase_changed, emit_supplier_changed
    emit_purchase_changed(pid)
    emit_supplier_changed(int(row["supplier_id"]))
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    spawn_tracked("audit.purchase_deleted", async_log_event(
        "purchase.deleted", scope="purchase", thread_id=pid,
        actor_type="web_user", actor_id=actor, source="purchase.deleted",
        payload={"supplier_id": row["supplier_id"], "total": row.get("total")}))
    return web.json_response({"ok": True})
