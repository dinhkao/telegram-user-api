"""Thu tiền GỘP nhiều đơn của 1 khách trong 1 giao dịch (bulk payment).

Người dùng mở từ chi tiết 1 đơn → trang #/order/:id/thanh-toan lấy khách của đơn
đó + MỌI đơn của khách CÒN THIẾU thanh toán → người dùng chọn các đơn muốn thu, nhập
1 tổng số tiền → client phân bổ theo chiều sắp xếp người dùng chọn. Xác nhận:
  • Tạo ĐÚNG 1 phiếu đặt hàng + thanh toán KiotViet cho TOÀN BỘ số tiền.
  • Chia thành N phiếu thu local (mỗi đơn 1 phiếu) cùng 1 payment_batch_id + cùng
    kiotvietData → xoá batch chỉ xoá KiotViet 1 lần (order_api_payments).
  • Tiền mặt: 1 phiếu sổ quỹ cho cả giao dịch (gắn payment_batch_id).
  • Cập nhật task nhận/nộp tiền, Firebase, realtime, công nợ (resync nền phân bổ nợ
    SAU cho cả loạt qua debt_sync._patch_batch_new_debt).

Nối: payment_store.domain, api_helpers.payment_core, quy_store, order_commands_v3
(_auto_complete_tasks_core), kiotviet, debt_sync. Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid

from aiohttp import web

from order_db import _get_connection, get_order_by_thread_id, get_customer_by_key
from payment_store.domain import method_params, resolve_payment_target
from server_app.customer_feed import _order_total_num
from server_app.order_api_common import apply_web_actor, is_office_request

log = logging.getLogger("server")


def _order_label(data: dict) -> str:
    """Nhãn ngắn gọn cho 1 đơn trong danh sách nợ (tên vài SP đầu)."""
    items = data.get("invoice") or data.get("san_pham") or []
    names = [str(it.get("sp") or it.get("ten") or "").strip() for it in items]
    names = [n for n in names if n]
    if not names:
        return ""
    label = ", ".join(names[:2])
    if len(names) > 2:
        label += f" +{len(names) - 2}"
    return label


def _paid_total(data: dict) -> int:
    """Tổng các phiếu thu local hợp lệ của đơn."""
    total = 0
    for payment in data.get("payments") or []:
        try:
            total += int(payment.get("amount") or 0)
        except (AttributeError, TypeError, ValueError):
            continue
    return total


def _load_customer_debt_orders(conn, key: str) -> tuple[list[dict], list[dict]]:
    """Đơn của khách `key` ĐANG NỢ (tổng thu < tổng đơn), cũ→mới — chia 2 nhóm:
      • active: hiện trên trang thu tiền (được phân bổ tiền).
      • hidden: đã "ẩn khỏi trang thu tiền" (bypass_debt) — LOẠI khỏi phân bổ nhưng
        vẫn liệt kê để bật lại ngay trên trang (toggle 2 chiều).
    Cả hai: cùng khách, chưa xoá, KHÔNG bỏ theo dõi nợ, còn thiếu tiền.
    debt = tổng đơn trừ tổng các phiếu thu đã có."""
    rows = conn.execute(
        "SELECT o.firebase_key, o.thread_id, o.channel_id, o.message_id, o.json, o.updated_at FROM orders o WHERE ("
        " CAST(json_extract(o.json,'$.khach_hang_id') AS TEXT) = ?"
        " OR CAST(json_extract(o.json,'$.khID') AS TEXT) = ? ) AND o.deleted_at IS NULL",
        (key, key),
    ).fetchall()
    from server_app.orders_api import _build_order_row
    active: list[dict] = []
    hidden: list[dict] = []
    for r in rows:
        tid = r["thread_id"]
        if tid is None:
            continue
        try:
            data = json.loads(r["json"])
        except (TypeError, ValueError):
            continue
        bt = data.get("bo_theo_doi_no")
        if bt in (1, True, "1", "true"):
            continue
        total = _order_total_num(data)
        if total <= 0:
            continue
        debt = total - _paid_total(data)
        if debt <= 0:
            continue
        bypass = data.get("bypass_debt") in (1, True, "1", "true")
        # Tái dùng đúng shape card dashboard để text, status icons và thumbnail
        # trên trang thu tiền luôn khớp với danh sách đơn.
        card = _build_order_row(r)
        rec = {
            "thread_id": tid,
            "created": data.get("created"),
            "total": total,
            "debt": debt,
            "label": _order_label(data),
            "text": card.get("text") or "",
            "task_icons": card.get("task_icons") or "",
            "soan_img_ids": card.get("soan_img_ids") or [],
            "nop_img_id": card.get("nop_img_id"),
            "bypass_debt": bypass,
        }
        (hidden if bypass else active).append(rec)
    # cũ → mới (feed dùng created; fallback thread_id để ổn định)
    from server_app.customer_feed import _ts_key
    _order_sort = lambda o: (_ts_key(o["created"]) or float(o["thread_id"]))
    active.sort(key=_order_sort)
    hidden.sort(key=_order_sort)
    from server_app.orders_api import _attach_thumbs
    _attach_thumbs(conn, active)
    _attach_thumbs(conn, hidden)
    return active, hidden


async def payment_context_handler(request: web.Request):
    """GET /api/order/{thread_id}/payment-context — khách của đơn + đơn đang nợ."""
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được thu tiền"}, status=403)
    try:
        thread_id = int(request.match_info.get("thread_id", ""))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)

    def _run():
        conn = _get_connection()
        src = get_order_by_thread_id(conn, thread_id)
        if not src:
            return {"ok": False, "error": "Không tìm thấy đơn", "status": 404}
        kh_id_fb = src.get("khach_hang_id") or src.get("khID")
        customer = get_customer_by_key(conn, str(kh_id_fb)) if kh_id_fb else None
        _, kv_id, kh_name, err = resolve_payment_target(src, customer)
        if err:
            return {"ok": False, "error": err, "status": 400}
        orders, hidden = _load_customer_debt_orders(conn, str(kh_id_fb))
        debt = (customer or {}).get("debt")
        return {
            "ok": True,
            "source_thread_id": thread_id,
            "customer": {"key": str(kh_id_fb), "name": kh_name, "kv_id": kv_id, "debt": debt},
            "orders": orders,
            "hidden_orders": hidden,
            # Tổng nợ là snapshot trên khách, KHÔNG cộng từ danh sách đơn bên dưới.
            "total_debt": debt if debt is not None else 0,
        }

    res = await asyncio.to_thread(_run)
    status = res.pop("status", 200)
    return web.json_response(res, status=status)


def _record_batch_cash_receipt(conn, source_thread_id, amount, batch_id, kh_id_fb, kh_name, n_orders, actor_name):
    """1 phiếu thu sổ quỹ cho CẢ giao dịch thu gộp (tiền mặt) → gắn payment_batch_id."""
    from quy_store import create_quy_table, migrate_quy_table, create_receipt
    create_quy_table(conn)
    migrate_quy_table(conn)
    note = f"Thu tiền mặt gộp {n_orders} đơn (đơn nguồn #{source_thread_id})" + (f" - {kh_name}" if kh_name else "")
    create_receipt(
        conn, type="thu", amount=int(amount), note=note, source="order",
        order_thread_id=int(source_thread_id), payment_batch_id=str(batch_id),
        customer_key=None if kh_id_fb is None else str(kh_id_fb),
        customer_name=kh_name, created_by=str(actor_name or ""),
    )
    from server_app.realtime import emit_quy_changed
    emit_quy_changed()


async def _process_bulk_payment(source_thread_id: int, method: str, amount: int,
                                allocations: list[dict], user_id) -> dict:
    """Lõi thu gộp (DB + KiotViet). Trả dict kết quả (giống _process_payment_core).

    RE-VALIDATE mọi đơn theo DB mới nhất TRƯỚC khi chạm KiotViet (chống dữ liệu đổi
    đồng thời). Chỉ tạo 1 phiếu KiotViet nếu qua hết kiểm tra."""
    from order_commands_v3 import _auto_complete_tasks_core
    from kiotviet import get_customer_debt_kv, create_order_with_payment
    from payment_store.domain import build_payment_record
    from payment_db import add_payment
    from firebase_sync import set_order as fb_set_order
    from server_app.realtime import emit_customer_changed, emit_order_changed

    conn = _get_connection()
    actor_name = str(user_id) if user_id else "API"
    account_id, method_label = method_params(method)
    result = {"success": False, "error": None, "source_thread_id": source_thread_id,
              "amount": int(amount), "method": method, "method_label": method_label,
              "kv_code": None, "old_debt": None, "new_debt": None, "kh_name": None,
              "batch_id": None, "allocations": []}

    if method not in ("Cash", "Transfer"):
        result["error"] = "Phương thức không hợp lệ"
        return result

    # 1. Đơn nguồn → khách → KiotViet id
    src = get_order_by_thread_id(conn, source_thread_id)
    if not src:
        result["error"] = "Không tìm thấy đơn nguồn"
        return result
    kh_id_fb_pre = src.get("khach_hang_id") or src.get("khID")
    customer = get_customer_by_key(conn, str(kh_id_fb_pre)) if kh_id_fb_pre else None
    kh_id_fb, kv_id, kh_name, err = resolve_payment_target(src, customer)
    if err:
        result["error"] = err
        return result
    result["kh_name"] = kh_name

    # 2. Re-validate phân bổ theo DB mới nhất (chống race) — LỖI trước KiotViet
    try:
        allocs = [(int(a["thread_id"]), int(a["amount"])) for a in (allocations or [])]
    except (TypeError, ValueError, KeyError):
        result["error"] = "Phân bổ không hợp lệ"
        return result
    if not allocs:
        result["error"] = "Không có đơn nào để thu"
        return result
    if any(amt <= 0 for _, amt in allocs):
        result["error"] = "Số tiền phân bổ phải lớn hơn 0"
        return result
    total_alloc = sum(amt for _, amt in allocs)
    if total_alloc != int(amount):
        result["error"] = "Tổng phân bổ không khớp số tiền"
        return result
    seen = set()
    validated: list[tuple[int, int]] = []
    for tid, amt in allocs:
        if tid in seen:
            result["error"] = f"Đơn #{tid} bị lặp trong phân bổ"
            return result
        seen.add(tid)
        o = get_order_by_thread_id(conn, tid)
        if not o or o.get("deleted_at"):
            result["error"] = f"Đơn #{tid} không còn — tải lại trang"
            return result
        bt = o.get("bo_theo_doi_no")
        if bt in (1, True, "1", "true"):
            result["error"] = f"Đơn #{tid} đã bỏ theo dõi nợ — tải lại trang"
            return result
        bypass = o.get("bypass_debt")
        if bypass in (1, True, "1", "true"):
            result["error"] = f"Đơn #{tid} đã được bỏ qua khi thu tiền — tải lại trang"
            return result
        okh = o.get("khach_hang_id") or o.get("khID")
        if str(okh) != str(kh_id_fb):
            result["error"] = f"Đơn #{tid} không thuộc khách này — tải lại trang"
            return result
        total = _order_total_num(o)
        remaining = total - _paid_total(o)
        if remaining <= 0:
            result["error"] = f"Đơn #{tid} đã thanh toán đủ — tải lại trang"
            return result
        if amt > remaining:
            result["error"] = f"Phân bổ đơn #{tid} vượt số tiền còn thiếu — tải lại trang"
            return result
        validated.append((tid, amt))

    # 3. Nợ TRƯỚC từ KiotViet (best-effort)
    old_debt = None
    try:
        old_debt = get_customer_debt_kv(kv_id).get("debt")
        result["old_debt"] = old_debt
    except Exception as e:
        log.warning("bulk pay: fetch old debt kv=%s lỗi: %s", kv_id, e)

    # 4. TẠO ĐÚNG 1 phiếu KiotViet cho TOÀN BỘ số tiền
    try:
        kv_res = create_order_with_payment(
            customer_id=kv_id, method=method, total_payment=total_alloc, account_id=account_id)
    except Exception as e:
        log.error("bulk pay: create_order_with_payment lỗi: %s", e)
        result["error"] = f"Lỗi tạo thanh toán KiotViet: {e}"
        return result
    if not kv_res:
        result["error"] = "Không thể tạo thanh toán trên KiotViet"
        return result
    result["kv_code"] = kv_res.get("code", "N/A")

    # 5. batch id (1 giao dịch)
    import time as _time
    batch_id = f"batch_{int(_time.time())}_{uuid.uuid4().hex[:8]}"
    result["batch_id"] = batch_id

    # 6. Chia thành N phiếu thu local — nợ TRƯỚC/SAU từng phiếu suy từ old_debt +
    # số đã phân bổ luỹ kế (đơn cũ trước); resync nền sẽ chốt lại từ KiotViet.
    cum = 0
    first_payment_id = None
    for tid, amt in validated:
        old_i = (old_debt - cum) if old_debt is not None else None
        new_i = (old_debt - cum - amt) if old_debt is not None else None
        rec = build_payment_record(amt, method, kv_res, actor_name, old_debt=old_i, new_debt=new_i)
        rec["payment_batch_id"] = batch_id
        add_payment(conn, tid, rec)
        if first_payment_id is None:
            first_payment_id = rec.get("id")
        _auto_complete_tasks_core(conn, tid, user_id)
        try:
            o2 = get_order_by_thread_id(conn, tid)
            if o2:
                fb_set_order(tid, o2)
        except Exception as e:
            log.warning("bulk pay: firebase sync đơn #%s lỗi: %s", tid, e)
        emit_order_changed(tid)
        result["allocations"].append({"thread_id": tid, "amount": amt})
        cum += amt

    # 7. Tiền mặt → 1 phiếu sổ quỹ cho cả giao dịch
    if method == "Cash":
        try:
            _record_batch_cash_receipt(conn, source_thread_id, total_alloc, batch_id,
                                       kh_id_fb, kh_name, len(validated), actor_name)
        except Exception as e:
            log.warning("bulk pay: ghi sổ quỹ lỗi: %s", e)

    # 8. Nợ SAU từ KiotViet + cập nhật khách + resync nền (phân bổ nợ SAU cả loạt)
    try:
        new_debt = get_customer_debt_kv(kv_id).get("debt")
        result["new_debt"] = new_debt
        if new_debt is not None:
            from order_db import update_customer_debt
            update_customer_debt(conn, str(kh_id_fb), new_debt)
    except Exception as e:
        log.warning("bulk pay: fetch new debt kv=%s lỗi: %s", kv_id, e)
    emit_customer_changed(str(kh_id_fb))
    try:
        from server_app.debt_sync import schedule_debt_resync
        schedule_debt_resync(str(kh_id_fb), thread_id=source_thread_id, payment_id=first_payment_id)
    except Exception as e:
        log.warning("bulk pay: schedule resync lỗi: %s", e)

    result["success"] = True
    return result


async def bulk_payment_handler(request: web.Request):
    """POST /api/order/payment/bulk — thu gộp nhiều đơn. Body {source_thread_id,
    method('Cash'|'Transfer'), amount, allocations:[{thread_id, amount}], user_id?}."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được thu tiền"}, status=403)
    apply_web_actor(request, body)
    source_thread_id = body.get("source_thread_id")
    method = body.get("method")
    amount = body.get("amount")
    allocations = body.get("allocations")
    if not source_thread_id or not amount or not allocations:
        return web.json_response({"ok": False, "error": "Thiếu source_thread_id / amount / allocations"}, status=400)
    try:
        result = await _process_bulk_payment(int(source_thread_id), method, int(amount),
                                             allocations, body.get("user_id"))
    except Exception as e:
        log.error("Bulk payment API error: %s", e, exc_info=True)
        return web.json_response({"ok": False, "error": str(e)}, status=500)
    if not result["success"]:
        # dữ liệu đổi đồng thời / đơn không hợp lệ → 409 để client biết cần tải lại
        return web.json_response({"ok": False, "error": result["error"]}, status=409)

    # Một giao dịch thu gộp làm thay đổi N đơn: ghi event riêng cho TỪNG đơn,
    # thay vì chỉ dựa vào request HTTP vốn không có một thread_id duy nhất.
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    audit_actor = str(request.get("web_user") or body.get("user_id") or "web")
    for allocation in result["allocations"]:
        tid = int(allocation["thread_id"])
        spawn_tracked("audit.order_bulk_payment", async_log_event(
            "order.bulk_payment", scope="order", thread_id=tid,
            actor_type="web_user" if request.get("web_user") else "http_client",
            actor_id=audit_actor, source="order.payment.bulk",
            payload={
                "amount": allocation["amount"], "method": result["method"],
                "batch_id": result["batch_id"],
                "source_thread_id": result["source_thread_id"],
            },
        ), {"thread_id": tid, "batch_id": result["batch_id"]})

    # Phiếu thu PNG + thông báo cho ĐƠN NGUỒN (tổng giao dịch) — chạy nền, không chặn.
    from server_app import state
    try:
        from server_app.receipt_image import add_receipt_image_to_gallery
        spawn_tracked("bulkpay.receipt.gallery", add_receipt_image_to_gallery(
            thread_id=result["source_thread_id"], customer_name=result["kh_name"],
            payment_amount=result["amount"], old_debt=result["old_debt"], new_debt=result["new_debt"]),
            {"thread_id": result["source_thread_id"]})
    except Exception as e:  # noqa: BLE001
        log.warning("bulk pay: lưu phiếu thu gallery lỗi: %s", e)
    if state._client is not None:
        try:
            from receipt_print import send_payment_receipt
            spawn_tracked("bulkpay.receipt", send_payment_receipt(
                client=state._client, thread_id=result["source_thread_id"],
                customer_name=result["kh_name"], payment_amount=result["amount"],
                old_debt=result["old_debt"], new_debt=result["new_debt"]),
                {"thread_id": result["source_thread_id"]})
        except Exception as e:  # noqa: BLE001
            log.warning("bulk pay: gửi phiếu thu lỗi: %s", e)

    return web.json_response({
        "ok": True, "source_thread_id": result["source_thread_id"], "amount": result["amount"],
        "method": result["method"], "method_label": result["method_label"], "kv_code": result["kv_code"],
        "old_debt": result["old_debt"], "new_debt": result["new_debt"], "batch_id": result["batch_id"],
        "allocations": result["allocations"],
    })
