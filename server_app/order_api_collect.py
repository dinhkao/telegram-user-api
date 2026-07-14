"""Thu tiền HÀNG LOẠT nhiều KHÁCH cùng lúc (trang #/thu-tien, menu ☰ Thêm).

Khác với thu gộp 1 khách (order_api_bulk_payment, vào từ 1 đơn): trang này liệt kê
MỌI khách đang có đơn nợ → văn phòng tick nhiều khách + số tiền mỗi khách → tạo
hàng loạt phiếu thu trong 1 lần bấm. Mỗi khách là 1 giao dịch thu gộp ĐỘC LẬP:
fan-out vào đúng lõi cũ `_process_bulk_payment` (1 phiếu KiotViet + N phiếu thu
local cùng batch_id + sổ quỹ + resync nợ nền) — KHÔNG thêm bảng mới, tận dụng hạ
tầng batch có sẵn (xoá batch, feed, cashbox, lịch sử đều chạy như thu gộp 1 khách).

Số thu mỗi khách bị CHẶN TRẦN theo tồn nợ thực của các đơn (collectable = Σ còn
thiếu của đơn active) vì tiền chỉ phân bổ được vào đơn; nợ KiotViet chỉ để tham
chiếu. Các khách chạy TUẦN TỰ (KiotViet dùng urllib đồng bộ) — lỗi 1 khách không
chặn khách khác, trả kết quả từng khách. Cap `_MAX_BATCH` khách/lần.

Nối: order_api_bulk_payment (_process_bulk_payment, _paid_total), customer_feed
(_order_total_num), payment_store.domain (allocate_payment), order_db, audit_log.
Đăng ký ở server_app/app_factory.
"""
from __future__ import annotations

import asyncio
import json
import logging

from aiohttp import web

from order_db import _get_connection, get_customer_by_key
from payment_store.domain import allocate_payment
from server_app.customer_feed import _order_total_num, _ts_key
from server_app.order_api_bulk_payment import _paid_total, _process_bulk_payment
from server_app.order_api_common import apply_web_actor, is_office_request

log = logging.getLogger("server")

# Trần số khách 1 lần thu loạt: KiotViet gọi đồng bộ nên loạt lớn = server bận lâu.
_MAX_BATCH = 60


def _active_remaining(data: dict) -> int | None:
    """Số tiền CÒN THIẾU của 1 đơn nếu đơn ĐANG NỢ và KHÔNG bị loại, ngược lại None.

    Cùng luật lọc với order_api_bulk_payment._load_customer_debt_orders:
    bỏ đơn `bo_theo_doi_no` / `bypass_debt`, tổng đơn > 0, còn thiếu > 0. Làm TRÒN
    XUỐNG (int) nên không bao giờ vượt số thực → qua được re-validate của lõi thu."""
    if data.get("bo_theo_doi_no") in (1, True, "1", "true"):
        return None
    if data.get("bypass_debt") in (1, True, "1", "true"):
        return None
    total = _order_total_num(data)
    if total <= 0:
        return None
    remaining = total - _paid_total(data)
    if remaining <= 0:
        return None
    rem = int(remaining)
    return rem if rem > 0 else None


def _active_debt_orders_light(conn, key: str) -> list[dict]:
    """Đơn ĐANG NỢ (active) của khách `key`, cũ→mới, chỉ {thread_id, debt, created}.

    Nhẹ (không dựng card/thumbnail như _load_customer_debt_orders) — chỉ đủ để phân
    bổ. Sắp cũ→mới để trả đủ đơn cũ trước (giống trang thu gộp)."""
    rows = conn.execute(
        "SELECT o.thread_id, o.json FROM orders o WHERE ("
        " CAST(json_extract(o.json,'$.khach_hang_id') AS TEXT) = ?"
        " OR CAST(json_extract(o.json,'$.khID') AS TEXT) = ? ) AND o.deleted_at IS NULL",
        (key, key),
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        tid = r["thread_id"]
        if tid is None:
            continue
        try:
            data = json.loads(r["json"])
        except (TypeError, ValueError):
            continue
        rem = _active_remaining(data)
        if rem is None:
            continue
        out.append({"thread_id": tid, "debt": rem, "created": data.get("created")})
    out.sort(key=lambda o: (_ts_key(o["created"]) or float(o["thread_id"])))
    return out


def _load_debtors(conn) -> dict:
    """1 lượt quét đơn → gom số CÓ THỂ THU theo khách; nối tên + nợ KiotViet.

    Trả {debtors, total_collectable, count}. Chỉ khách có collectable > 0 (thu được
    qua đơn). `blocked`=True khi khách chưa có kh_id KiotViet (không tạo được HĐ)."""
    # Bản đồ khách (≈343 dòng — quét nhanh trong bộ nhớ).
    custs: dict[str, dict] = {}
    for fk, jt in conn.execute("SELECT firebase_key, json FROM customers WHERE deleted_at IS NULL"):
        try:
            cd = json.loads(jt)
        except (TypeError, ValueError):
            continue
        custs[str(fk)] = {
            "name": cd.get("name") or cd.get("ten") or str(fk),
            "kv_debt": cd.get("debt"),
            "kh_id": cd.get("kh_id"),
        }
    # 1 lượt quét đơn → cộng collectable + đếm đơn theo khách.
    agg: dict[str, dict] = {}
    for r in conn.execute("SELECT json FROM orders WHERE deleted_at IS NULL AND json IS NOT NULL"):
        try:
            data = json.loads(r["json"])
        except (TypeError, ValueError):
            continue
        key = data.get("khach_hang_id") or data.get("khID")
        if not key:
            continue
        rem = _active_remaining(data)
        if rem is None:
            continue
        e = agg.setdefault(str(key), {"collectable": 0, "order_count": 0})
        e["collectable"] += rem
        e["order_count"] += 1
    debtors: list[dict] = []
    for key, e in agg.items():
        c = custs.get(key) or {}
        debtors.append({
            "key": key,
            "name": c.get("name") or key,
            "kv_debt": c.get("kv_debt"),
            "collectable": e["collectable"],
            "order_count": e["order_count"],
            "blocked": not c.get("kh_id"),
        })
    debtors.sort(key=lambda d: d["collectable"], reverse=True)
    total = sum(d["collectable"] for d in debtors)
    return {"debtors": debtors, "total_collectable": total, "count": len(debtors)}


async def debtors_handler(request: web.Request):
    """GET /api/collect/debtors — mọi khách có đơn đang nợ (thu được qua đơn)."""
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được thu tiền"}, status=403)

    def _run():
        conn = _get_connection()
        try:
            return _load_debtors(conn)
        finally:
            conn.close()

    res = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, **res})


def _prep_collection(key: str, req_amt: int) -> dict:
    """Chuẩn bị phân bổ cho 1 khách (chạy trong thread): tên + allocations + số thu
    thực (chặn trần theo collectable). Không chạm KiotViet."""
    conn = _get_connection()
    try:
        cust = get_customer_by_key(conn, key)
        name = (cust or {}).get("name") or key
        orders = _active_debt_orders_light(conn, key)
    finally:
        conn.close()
    if not orders:
        return {"name": name, "ok": False, "error": "Không còn đơn để thu"}
    collectable = sum(o["debt"] for o in orders)
    amt = min(int(req_amt), collectable)
    if amt <= 0:
        return {"name": name, "ok": False, "error": "Không có gì để thu"}
    allocations = allocate_payment(orders, amt)
    return {
        "name": name, "ok": True, "amt": amt, "collectable": collectable,
        "allocations": allocations, "source": allocations[0]["thread_id"],
    }


async def _collect_one(key: str, method: str, req_amt: int, user_id) -> dict:
    """Thu cho 1 khách: chuẩn bị (thread) → fan-out vào lõi thu gộp cũ. Không ném:
    mọi lỗi gói vào kết quả để loạt tiếp tục."""
    base = {
        "key": key, "name": key, "requested": int(req_amt), "collected": 0,
        "order_count": 0, "kv_code": None, "new_debt": None, "batch_id": None,
        "capped": False, "allocations": [],
    }
    try:
        prep = await asyncio.to_thread(_prep_collection, key, int(req_amt))
    except Exception as e:  # noqa: BLE001
        log.error("collect prep key=%s lỗi: %s", key, e, exc_info=True)
        return {**base, "ok": False, "error": "Lỗi chuẩn bị phân bổ"}
    base["name"] = prep.get("name") or key
    if not prep.get("ok"):
        return {**base, "ok": False, "error": prep.get("error") or "Không thu được"}
    amt = int(prep["amt"])
    allocations = prep["allocations"]
    try:
        res = await _process_bulk_payment(int(prep["source"]), method, amt, allocations, user_id)
    except Exception as e:  # noqa: BLE001
        log.error("collect one key=%s lỗi: %s", key, e, exc_info=True)
        return {**base, "ok": False, "error": str(e)}
    if not res.get("success"):
        return {**base, "ok": False, "error": res.get("error") or "Thu thất bại"}
    done = res.get("allocations") or []
    return {
        **base, "ok": True, "error": None,
        "name": res.get("kh_name") or base["name"],
        "collected": amt, "order_count": len(done),
        "kv_code": res.get("kv_code"), "new_debt": res.get("new_debt"),
        "batch_id": res.get("batch_id"), "capped": amt < int(req_amt),
        "allocations": done,
    }


def _audit_collect(request: web.Request, body: dict, r: dict, method: str) -> None:
    """Ghi event order.bulk_payment cho TỪNG đơn của 1 khách thu thành công (để hiện
    ở Lịch sử thao tác) — dùng lại nhãn/định dạng thu gộp có sẵn (event_format)."""
    from audit_log import async_log_event
    from server_app.tasks import spawn_tracked
    actor = str(request.get("web_user") or body.get("user_id") or "web")
    allocs = r.get("allocations") or []
    if not allocs:
        return
    source_tid = int(allocs[0]["thread_id"])
    for a in allocs:
        tid = int(a["thread_id"])
        spawn_tracked("audit.order_collect_batch", async_log_event(
            "order.bulk_payment", scope="order", thread_id=tid,
            actor_type="web_user" if request.get("web_user") else "http_client",
            actor_id=actor, source="order.payment.collect",
            payload={
                "amount": a["amount"], "method": method,
                "batch_id": r["batch_id"], "source_thread_id": source_tid,
            },
        ), {"thread_id": tid, "batch_id": r["batch_id"]})


async def collect_batch_handler(request: web.Request):
    """POST /api/collect/batch — thu hàng loạt nhiều khách. Body {method('Cash'|
    'Transfer'), collections:[{customer_key, amount}], user_id?}. Trả kết quả từng
    khách (ok/collected/capped/error) + tổng."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới được thu tiền"}, status=403)
    apply_web_actor(request, body)
    method = body.get("method")
    if method not in ("Cash", "Transfer"):
        return web.json_response({"ok": False, "error": "Phương thức không hợp lệ"}, status=400)
    collections = body.get("collections")
    if not isinstance(collections, list) or not collections:
        return web.json_response({"ok": False, "error": "Thiếu danh sách thu"}, status=400)
    if len(collections) > _MAX_BATCH:
        return web.json_response(
            {"ok": False, "error": f"Quá nhiều khách 1 lần (tối đa {_MAX_BATCH}) — chia nhỏ lại"},
            status=400)
    user_id = body.get("user_id")

    # Chuẩn hoá + khử trùng khách (giữ khoản đầu tiên), bỏ khoản không hợp lệ.
    parsed: list[tuple[str, int]] = []
    seen: set[str] = set()
    for c in collections:
        try:
            key = str((c or {}).get("customer_key") or "").strip()
            amt = int((c or {}).get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if not key or amt <= 0 or key in seen:
            continue
        seen.add(key)
        parsed.append((key, amt))
    if not parsed:
        return web.json_response({"ok": False, "error": "Không có khoản thu hợp lệ"}, status=400)

    results: list[dict] = []
    for key, amt in parsed:
        try:
            r = await _collect_one(key, method, amt, user_id)
        except Exception as e:  # noqa: BLE001
            log.error("collect batch key=%s lỗi: %s", key, e, exc_info=True)
            r = {"key": key, "name": key, "ok": False, "requested": amt, "collected": 0,
                 "order_count": 0, "kv_code": None, "new_debt": None, "batch_id": None,
                 "capped": False, "error": str(e), "allocations": []}
        results.append(r)
        if r.get("ok") and r.get("batch_id"):
            try:
                _audit_collect(request, body, r, method)
            except Exception as e:  # noqa: BLE001
                log.warning("collect batch audit key=%s lỗi: %s", key, e)
        # Nhường loop để realtime/emit của khách vừa xong được đẩy đi.
        await asyncio.sleep(0)

    ok = [r for r in results if r.get("ok")]
    # Bỏ allocations khỏi payload trả về (client không cần, giảm kích thước).
    slim = [{k: v for k, v in r.items() if k != "allocations"} for r in results]
    return web.json_response({
        "ok": True,
        "ok_count": len(ok),
        "fail_count": len(results) - len(ok),
        "total_collected": sum(r["collected"] for r in ok),
        "total_requested": sum(amt for _, amt in parsed),
        "results": slim,
    })
