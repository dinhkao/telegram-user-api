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


def _order_total_num(data: dict) -> int:
    """Tổng đơn dạng số — cùng nguồn với row dashboard (print_content.tongthanhtoan,
    fallback Σ sl×giá của invoice)."""
    pc = (data.get("hoadon") or {}).get("print_content") or {}
    t = str(pc.get("tongthanhtoan") or "").replace(".", "")
    if t.isdigit() and int(t) > 0:
        return int(t)
    try:
        return sum(int(it.get("price", 0) or 0) * int(it.get("sl", it.get("quantity", 0)) or 0)
                   for it in data.get("invoice") or [])
    except (TypeError, ValueError):
        return 0


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


def _fill_debt_chain(events: list[dict], current_debt) -> None:
    """Điền debt_after cho MỌI sự kiện (events theo thời gian TĂNG dần, mutate).

    Mỗi event: {delta, stored (số gốc hoặc None)} → gắn thêm debt_after + est.
    Mốc = stored + mốc ảo cuối (current_debt). Tiến giữa các mốc, lùi trước mốc đầu.
    """
    n = len(events)
    _TOL = 1.0   # sai số làm tròn cho phép khi đối chiếu 2 mốc

    # TIỀN XỬ LÝ — loạt phiếu thu dính nợ TRÙNG (bug resync: thu nhiều phiếu liền
    # tay → resync +6s của từng phiếu đều đọc ra cùng số nợ CUỐI từ KV → các phiếu
    # trước bị ghi trùng). Nợ sau 2 khoản thu >0 liên tiếp KHÔNG THỂ bằng nhau nếu
    # không có gì cộng nợ chen giữa → số của phiếu TRƯỚC là rác → bỏ (stored=None)
    # cho nội suy neo mốc điền lại (có kiểm chứng cân đoạn như thường).
    last_pay = None        # index phiếu thu gần nhất còn stored
    pos_delta_since = False   # có sự kiện cộng nợ chen giữa từ phiếu đó tới đây?
    for i, e in enumerate(events):
        if e.get("delta", 0) > 0:
            pos_delta_since = True
        if e.get("kind") != "payment" or e.get("stored") is None:
            continue
        if (last_pay is not None and not pos_delta_since and e.get("delta", 0) < 0
                and abs(float(events[last_pay]["stored"]) - float(e["stored"])) <= _TOL):
            events[last_pay]["stored"] = None
        last_pay = i
        pos_delta_since = False

    for e in events:
        s = e.get("stored")
        e["debt_after"] = float(s) if s is not None else None
        e["est"] = s is None
    stored_idx = [i for i, e in enumerate(events) if not e["est"]]
    if not stored_idx and current_debt is None:
        return   # không có mốc nào — để None hết ('—')

    # GIỮA 2 mốc lưu: chỉ điền khi đoạn CÂN — mốc_trước + Σdelta == mốc_sau.
    # Không cân = có biến động ngoài app (chỉnh nợ tay KV, HĐ ngoài, xoá HĐ…)
    # → số nội suy trong đoạn đó KHÔNG tin được → giữ '—' (không hiện số sai).
    for a, b in zip(stored_idx, stored_idx[1:]):
        expected = events[a]["debt_after"] + sum(events[k]["delta"] for k in range(a + 1, b + 1))
        if abs(expected - events[b]["debt_after"]) <= _TOL:
            running = events[a]["debt_after"]
            for k in range(a + 1, b):
                running += events[k]["delta"]
                events[k]["debt_after"] = running
        # lệch → bỏ trống cả đoạn (est giữ None)

    # ĐUÔI (sau mốc lưu cuối): LÙI từ mốc ảo "hiện tại" (nợ KV đang có). Có mốc lưu
    # cuối để đối chiếu → cũng phải CÂN mới điền; không có mốc lưu nào → điền thẳng
    # nhưng bỏ nếu lòi số ÂM (nợ âm = chuỗi chắc chắn thiếu sự kiện).
    if current_debt is not None:
        last = stored_idx[-1] if stored_idx else -1
        vals: list[float] = []
        running = float(current_debt)
        for i in range(n - 1, last, -1):
            vals.append(running)
            running -= events[i]["delta"]
        ok = (abs(running - events[last]["debt_after"]) <= _TOL) if last >= 0 else all(v >= 0 for v in vals)
        if ok:
            for j, i in enumerate(range(n - 1, last, -1)):
                events[i]["debt_after"] = vals[j]

    # ĐẦU (trước mốc đầu): LÙI một phía, không có gì đối chiếu → chỉ điền khi
    # không lòi số âm.
    first = stored_idx[0] if stored_idx else n
    if first > 0 and first < n and events[first]["debt_after"] is not None:
        vals2: list[float] = []
        running = events[first]["debt_after"]
        for i in range(first - 1, -1, -1):
            running = running - events[i + 1]["delta"]
            vals2.append(running)
        if all(v >= 0 for v in vals2):
            for j, i in enumerate(range(first - 1, -1, -1)):
                if events[i]["debt_after"] is None:
                    events[i]["debt_after"] = vals2[j]


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
        events.append({
            "ts": _ts_key(data.get("created")) or float(tid), "kind": "order", "tid": tid,
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
            events.append({
                "ts": _ts_key(p.get("created_at")), "kind": "payment", "tid": tid,
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
                    "items": rt.get("items") or [], "code": rt.get("kv_invoice_code") or "",
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
