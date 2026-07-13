"""Feed ĐƠN + THANH TOÁN của 1 khách, gộp 1 dòng thời gian (trang chi tiết khách).

GET /api/customers/{key}/feed?page= → items xen kẽ theo thời gian giảm dần:
  {kind:'order', ts, order:<row như dashboard>, debt_after, debt_est} |
  {kind:'payment', ts, thread_id, amount, method, code, by, at,
   old_debt, new_debt, debt_after, debt_est}

── SỐ NỢ SAU MỖI SỰ KIỆN (debt_after) — 2 nguồn ─────────────────────────────────
1. SỐ GỐC (debt_est=False): số KiotViet ĐÃ LƯU tại thời điểm sự kiện —
   payment.new_debt (ghi lúc thu, resync nền vá), hoặc snapshot HĐ + tổng đơn.
2. SỐ TÍNH LẠI (debt_est=True — user cho phép 2026-07-08 cho BẢN GHI CŨ thiếu số,
   "nhớ note kỹ"): nội suy NEO VÀO MỐC THẬT — quy tắc:
   • Delta mỗi sự kiện: đơn CÓ HĐ KiotViet → +tổng đơn; đơn KHÔNG HĐ → 0 (không
     đụng nợ KV); thanh toán → −amount.
   • MỐC = sự kiện có số gốc + 1 mốc ảo "hiện tại" = công nợ KV đang lưu của khách.
   • Giữa 2 mốc: chạy TIẾN từ mốc trước (cộng dồn delta); gặp mốc sau thì RESET
     về số gốc của mốc đó (số thật luôn thắng số tính). Trước mốc đầu: chạy LÙI.
   • Sự kiện KV bị chỉnh tay giữa 2 mốc → số est trong đoạn đó lệch, nhưng tự
     re-anchor ở mốc kế → sai số không lan. UI hiện '≈' trước số est để phân biệt.
   • Mốc đúng-số-nhưng-SAI-CHỖ (HĐ KiotViet tạo trễ, sau phiếu thu kế đó →
     khDebt chụp lúc nợ đã trả) → demote có kiểm chứng rồi nội suy lại — xem
     server_app/feed_debt._demote_misplaced_anchors (logic thuần, unit-tested).

Đơn của 1 khách ít (vài chục~trăm) nên dựng cả chuỗi trong RAM rồi phân trang;
row đơn dựng bằng _build_order_row + thumbs — y hệt dashboard để client tái dùng
card. Nối: server_app.orders_api, server_app.orders_db, bảng customers (mốc ảo).
Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

from aiohttp import web

from server_app.feed_debt import _fill_debt_chain

_PAGE = 20


def _ts_key(v) -> float:
    """Chuỗi thời gian bất kỳ (ISO / epoch s hoặc ms / rỗng) → epoch float để sort."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        x = float(v)
        return x / 1000.0 if x > 1e12 else x
    s = str(v).strip()
    if not s:
        return 0.0
    try:
        x = float(s)
        return x / 1000.0 if x > 1e12 else x
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _money_num(value) -> int:
    """Chuẩn hoá tiền lưu dạng số hoặc chuỗi ``9,430,000`` / ``9.430.000``."""
    if value is None or value == "":
        return 0
    try:
        if isinstance(value, str):
            value = value.strip().replace(",", "").replace(".", "")
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _order_total_num(data: dict) -> int:
    """Tổng tiền của riêng hóa đơn, trước nợ cũ.

    Công thức duy nhất của app: tiền hàng + PVC + VAT - chiết khấu. Hóa đơn đời
    cũ không còn ``invoice`` thì dùng ``print_content.tongtienhang``; tuyệt đối
    không dùng ``tongthanhtoan`` vì trường đó đã cộng ``no_truoc``.
    """
    items = data.get("invoice") or data.get("san_pham") or []
    goods = 0
    try:
        goods = sum(
            _money_num(it.get("price"))
            * _money_num(it.get("sl", it.get("quantity", 0)))
            for it in items
        )
    except (AttributeError, TypeError):
        goods = 0
    if not items:
        pc = (data.get("hoadon") or {}).get("print_content") or {}
        goods = _money_num(pc.get("tongtienhang"))
    return max(
        0,
        goods
        + _money_num(data.get("pvc"))
        + _money_num(data.get("vat"))
        - _money_num(data.get("discount")),
    )


def _current_debt(conn, key: str):
    """Công nợ KiotViet HIỆN TẠI của khách (mốc ảo cuối chuỗi). None nếu không có."""
    try:
        row = conn.execute(
            "SELECT json_extract(json, '$.debt') FROM customers WHERE firebase_key = ? AND deleted_at IS NULL",
            (key,),
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else None
    except Exception:
        return None


_VN = None


def _vn_day(ts: float) -> str:
    """Ngày VN (YYYY-MM-DD) của 1 epoch — cho lịch tháng."""
    global _VN
    if _VN is None:
        from datetime import timezone, timedelta
        _VN = timezone(timedelta(hours=7))
    return datetime.fromtimestamp(ts, _VN).strftime("%Y-%m-%d")


def _load_events(conn, key: str) -> list[dict]:
    """Toàn bộ sự kiện của khách (TĂNG dần thời gian) + debt_after đã điền."""
    events = _collect_events(conn, key)
    events.sort(key=lambda e: e["ts"])
    _fill_debt_chain(events, _current_debt(conn, key))
    return events


def _items_from_events(conn, chunk: list[dict]) -> list[dict]:
    """Sự kiện → item trả cho client (row đơn như dashboard + payment + nợ)."""
    from server_app.orders_api import _ROW_COLUMNS, _build_order_row, _attach_thumbs
    order_ids = [e["tid"] for e in chunk if e["kind"] == "order"]
    rows_by_id = {}
    if order_ids:
        qs = ",".join("?" * len(order_ids))
        rows = conn.execute(
            f"SELECT {_ROW_COLUMNS} FROM orders o WHERE o.thread_id IN ({qs})", order_ids
        ).fetchall()
        built = [_build_order_row(r) for r in rows]
        _attach_thumbs(conn, built)
        rows_by_id = {o["thread_id"]: o for o in built}
    items = []
    for e in chunk:
        da = e.get("debt_after")
        base = {"ts": e["ts"], "debt_after": da, "debt_est": bool(e.get("est")) if da is not None else False}
        if e["kind"] == "order":
            row = rows_by_id.get(e["tid"])
            if row:
                items.append({"kind": "order", "order": row, **base})
        elif e["kind"] == "return":
            items.append({"kind": "return", **e["ret"], **base})
        else:
            items.append({"kind": "payment", **e["pay"], **base})
    return items


def _collect_events(conn, key: str) -> list[dict]:
    # 1) sự kiện: mọi đơn (ts=created) + mọi payment trong blob (ts=created_at)
    # CAST AS TEXT: khach_hang_id trong blob khi là số (8) khi là chữ ('8')
    events: list[dict] = []
    for r in conn.execute(
        "SELECT o.thread_id, o.json FROM orders o "
        "WHERE CAST(json_extract(o.json, '$.khach_hang_id') AS TEXT) = ? AND o.deleted_at IS NULL",
        (key,),
    ).fetchall():
        tid = r["thread_id"]
        if tid is None:
            continue   # row hỏng/di sản
        try:
            data = json.loads(r["json"])
        except (TypeError, ValueError):
            continue
        total_num = _order_total_num(data)
        # đơn "có HĐ" (đã cộng vào nợ KV): field mới kiotvietInvoiceID, HOẶC dấu vết
        # HĐ đời cũ (hoadon.hd_code / kiotvietInvoiceCode / print_content có tổng)
        hd = data.get("hoadon") or {}
        has_kv = bool(data.get("kiotvietInvoiceID") or data.get("kiotvietInvoiceCode")
                      or hd.get("hd_code") or (hd.get("print_content") or {}).get("tongthanhtoan"))
        snapshot = data.get("khDebt", data.get("invoice_debt_snapshot"))
        stored = (float(snapshot) + total_num) if (snapshot is not None and has_kv and total_num) else None
        order_ts = _ts_key(data.get("created")) or float(tid)
        events.append({
            "ts": order_ts, "kind": "order", "tid": tid,
            # đơn KHÔNG có HĐ KiotViet không đụng nợ KV → delta 0
            "delta": float(total_num) if has_kv else 0.0,
            "stored": stored,
        })
        for p in data.get("payments") or []:
            nd = p.get("new_debt")
            by = str(p.get("createdBy") or p.get("by") or "")
            try:   # id thô (vd '6730500620') → tên hiển thị
                from bot_core.config import USER_NAMES
                by = USER_NAMES.get(by, by)
            except Exception:
                pass
            # payment đời Node ghi camelCase createdAt — vẫn là giờ THẬT
            pay_ts = _ts_key(p.get("created_at") or p.get("createdAt"))
            events.append({
                # payment di sản không có giờ nào → neo cạnh đơn của nó
                # (hơn là văng về 1970 đầu chuỗi); đánh dấu ts_guessed để
                # feed_debt không dùng vị trí ĐOÁN làm bằng chứng demote mốc thật
                "ts": pay_ts or (order_ts + 1.0), "ts_guessed": not pay_ts,
                "kind": "payment", "tid": tid,
                "delta": -float(p.get("amount") or 0),
                "stored": float(nd) if nd is not None else None,
                "pay": {
                    "thread_id": tid,
                    "amount": p.get("amount") or 0,
                    "method": p.get("method") or "",
                    "code": p.get("code") or "",
                    "by": by,
                    "at": p.get("created_at"),
                    "old_debt": p.get("old_debt"),
                    "new_debt": nd,
                },
            })

    # 2) phiếu TRẢ HÀNG (return_slips) — giảm nợ, mốc = debt_after (resync vá)
    try:
        from order_store.display import resolve_invoice_display
        from return_store import list_returns
        for rt in list_returns(conn, key):
            has_kv = bool(rt.get("kv_invoice_id"))
            events.append({
                "ts": _ts_key(rt.get("created_at")), "kind": "return", "tid": rt.get("thread_id"),
                # NHÁP (chưa HĐ KV) không đụng nợ → delta 0 (giống đơn không HĐ)
                "delta": -float(rt.get("total") or 0) if has_kv else 0.0,
                "stored": float(rt["debt_after"]) if (has_kv and rt.get("debt_after") is not None) else None,
                "ret": {
                    "id": rt["id"], "total": rt.get("total") or 0, "note": rt.get("note") or "",
                    # mã SP hiển thị = mã hiện hành
                    "items": resolve_invoice_display(rt.get("items") or [], conn),
                    "code": rt.get("kv_invoice_code") or "",
                    "by": rt.get("created_by") or "", "at": rt.get("created_at"),
                    "thread_id": rt.get("thread_id"),
                },
            })
    except Exception:
        pass   # bảng chưa có → bỏ qua

    return events


def _build_feed(conn, key: str, page: int):
    """Trang feed (GIẢM dần thời gian)."""
    events = _load_events(conn, key)
    events.reverse()
    total = len(events)
    chunk = events[(page - 1) * _PAGE: (page - 1) * _PAGE + _PAGE]
    return _items_from_events(conn, chunk), total


def _build_days(conn, key: str) -> list[dict]:
    """Đếm biến động theo NGÀY (lịch tháng): [{d:'YYYY-MM-DD', o: số đơn, p: số phiếu thu}]."""
    counts: dict[str, dict] = {}
    for e in _load_events(conn, key):
        d = _vn_day(e["ts"])
        c = counts.setdefault(d, {"d": d, "o": 0, "p": 0})
        c["o" if e["kind"] == "order" else "p"] += 1
    return sorted(counts.values(), key=lambda c: c["d"])


def _build_day_items(conn, key: str, day: str) -> list[dict]:
    """Mọi biến động của 1 ngày (popup lịch) — GIẢM dần thời gian."""
    events = [e for e in _load_events(conn, key) if _vn_day(e["ts"]) == day]
    events.reverse()
    return _items_from_events(conn, events)


async def customer_feed_handler(request: web.Request):
    key = request.match_info.get("key", "").strip()
    if not key:
        return web.json_response({"ok": False, "error": "thiếu key"}, status=400)
    try:
        page = max(1, int(request.query.get("page", "1")))
    except ValueError:
        page = 1

    days_mode = request.query.get("days")
    day = (request.query.get("day") or "").strip()

    def _run():
        from server_app.orders_db import get_orders_conn
        conn = get_orders_conn()
        try:
            if days_mode:
                return ("days", _build_days(conn, key))
            if day:
                return ("day", _build_day_items(conn, key, day))
            return ("page", _build_feed(conn, key, page))
        finally:
            conn.close()

    mode, res = await asyncio.to_thread(_run)
    if mode == "days":
        return web.json_response({"ok": True, "days": res})
    if mode == "day":
        return web.json_response({"ok": True, "items": res})
    items, total = res
    total_pages = max(1, -(-total // _PAGE))
    return web.json_response({"ok": True, "items": items, "page": page,
                              "total_pages": total_pages, "total": total})
