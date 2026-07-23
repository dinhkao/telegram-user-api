"""Cảnh báo THIẾU HÀNG — khi TẠO đơn hoặc SỬA hoá đơn, so số CẦN (invoice) với TỒN
kho (inventory_store.product_summary). Mã nào tồn < cần → push_bg (Notification
Center + FCM). Dedup theo $.stock_alert_state trong blob đơn để KHÔNG báo lặp khi
đơn đổi vì lý do khác (thanh toán, task, render lại…). Đơn ĐÃ GIAO thì bỏ qua hẳn —
đơn cũ bị đụng lại (gửi toa, bỏ theo dõi nợ, thu tiền…) không được báo thiếu oan
theo tồn kho hiện tại. Chạy nền, không chặn hot path.
Nối: order_store.serialization, order_store.schema, inventory_store, server_app.notify,
server_app.tasks, utils.db.
"""
from __future__ import annotations

import asyncio
import logging

from utils.db import get_connection

log = logging.getLogger("server")

_EPS = 1e-6


def _needs_from_invoice(order: dict) -> dict[str, float]:
    """Gom số CẦN theo mã SP (in hoa) từ các dòng hoá đơn của đơn."""
    needs: dict[str, float] = {}
    for it in order.get("invoice") or []:
        code = str(it.get("sp") or "").strip().upper()
        if not code:
            continue
        try:
            needs[code] = needs.get(code, 0.0) + float(it.get("sl") or 0)
        except (TypeError, ValueError):
            pass
    return needs


def _delivered(order: dict) -> bool:
    """Đơn đã qua bước GIAO HÀNG (done hoặc skip) — hàng đã rời kho từ trước nên
    so invoice với tồn HIỆN TẠI là vô nghĩa; mọi refresh về sau (gửi toa, bỏ theo
    dõi nợ, thanh toán…) không được báo thiếu."""
    st = (order.get("task_status") or {}).get("giao_hang") or {}
    return bool(st.get("done") or st.get("skip"))


def _compute(conn, thread_id: int):
    """Trong 1 transaction: đọc đơn + tồn, tính tập THIẾU, dedup theo dấu đã báo.
    Trả None nếu không cần báo (không thiếu, hoặc tập thiếu KHÔNG đổi); ngược lại
    trả {"short": {code: (need, have)}, "peek": <dòng đầu nội dung đơn>}."""
    from order_store.serialization import get_order_by_thread_id, _update_order_json_field
    order = get_order_by_thread_id(conn, thread_id)
    if not order or _delivered(order):
        return None
    needs = _needs_from_invoice(order)
    prev = order.get("stock_alert_state")
    prev = prev if isinstance(prev, dict) else {}
    if not needs:
        if prev:
            _update_order_json_field(conn, thread_id, "$.stock_alert_state", {})
        return None
    from inventory_store import product_summary, list_order_allocations
    avail: dict[str, float] = {}
    for s in product_summary(conn):
        code = str(s.get("product_code") or "").strip().upper()
        if not code:
            continue
        try:
            avail[code] = float(s.get("in_stock_total") or 0)
        except (TypeError, ValueError):
            avail[code] = 0.0
    # in_stock_total = tồn CÒN LẠI = quantity − Σ MỌI phân bổ (kể cả phần đã xuất cho
    # CHÍNH đơn này). Cộng lại phần của đơn này thì "khả dụng cho đơn" = tồn tự do +
    # phần đã giữ cho nó → đơn đã xuất đủ KHÔNG bị coi là thiếu (tránh báo oan lúc
    # chốt kho / phân bổ; phân bổ chỉ dời từ tự-do sang của-đơn nên have không đổi).
    own: dict[str, float] = {}
    for a in list_order_allocations(conn, thread_id):
        code = str(a.get("product_code") or "").strip().upper()
        if code:
            own[code] = own.get(code, 0.0) + float(a.get("quantity") or 0)
    short: dict[str, tuple[float, float]] = {}
    for code, need in needs.items():
        have = avail.get(code, 0.0) + own.get(code, 0.0)
        if have + _EPS < need:
            short[code] = (need, have)
    # Dấu đã báo = {code: round(need)} — chỉ báo lại khi TẬP THIẾU (mã + số cần) đổi
    cur = {c: round(n, 3) for c, (n, _h) in short.items()}
    if cur == prev:
        return None
    _update_order_json_field(conn, thread_id, "$.stock_alert_state", cur)
    if not short:
        return None
    peek = (order.get("text") or order.get("text_raw") or "").strip().split("\n", 1)[0][:60]
    return {"short": short, "peek": peek}


def _fmt(n: float) -> str:
    """Số gọn: 12.0 -> '12', 12.5 -> '12.5'."""
    return f"{int(n)}" if abs(n - int(n)) < _EPS else f"{n:g}"


async def _run(thread_id: int) -> None:
    def _work():
        conn = get_connection()
        try:
            from order_store.schema import transaction
            with transaction(conn):
                return _compute(conn, thread_id)
        finally:
            conn.close()
    try:
        res = await asyncio.to_thread(_work)
    except Exception as e:  # noqa: BLE001
        log.warning("stock_alert lỗi thread=%s: %s", thread_id, e)
        return
    if not res:
        return
    short = res["short"]
    codes = sorted(short)
    head = ", ".join(codes[:3]) + (f" +{len(codes) - 3}" if len(codes) > 3 else "")
    detail = "; ".join(f"{c}: cần {_fmt(short[c][0])}, còn {_fmt(short[c][1])}" for c in codes)
    peek = res.get("peek")
    body = f"Đơn {peek} — {detail}" if peek else detail
    from server_app.notify import push_bg
    push_bg(f"⚠️ Thiếu hàng: {head}", body, {"type": "stock_alert", "thread_id": thread_id})


def check_and_notify_bg(thread_id) -> None:
    """Lên lịch kiểm tra + báo THIẾU HÀNG chạy nền (không chặn handler gọi). Gọi ở
    các điểm tạo đơn / refresh đơn (web + Telegram)."""
    if not thread_id:
        return
    try:
        tid = int(thread_id)
    except (TypeError, ValueError):
        return
    from server_app.tasks import spawn_tracked
    spawn_tracked("stock_alert.check", _run(tid))
