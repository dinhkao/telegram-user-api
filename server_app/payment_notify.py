"""PUSH khi có người TẠO THANH TOÁN (phiếu thu) cho đơn: "💰 <người> nhận <số tiền>" +
dòng đầu nội dung đơn. Gọi SAU KHI ghi local thành công ở 2 lõi thu tiền
(order_commands_v3._process_payment_core — thu 1 đơn / lệnh tm; order_api_bulk_payment.
_process_bulk_payment_locked — thu gộp, thu nhanh, thu hàng loạt) → phiếu bị rollback
không bao giờ báo nhầm. Đi qua server_app.notify.push_bg (hàng đợi push bền).
Thu gộp nhiều đơn: ≤ MAX_EACH đơn → mỗi đơn 1 push; nhiều hơn → 1 push tổng.
Nội dung thuần: build_payment_notifs (tests/test_payment_notify.py).
"""
from __future__ import annotations

import asyncio
import logging

from utils.db import get_connection

log = logging.getLogger("server")
MAX_EACH = 3


def _money(n) -> str:
    try:
        return f"{int(n):,}".replace(",", ".") + "đ"
    except (TypeError, ValueError):
        return f"{n}đ"


def _peek(text: str) -> str:
    t = (text or "").strip()
    return t.split("\n", 1)[0].strip()[:80] if t else ""


def build_payment_notifs(actor: str, items: list[dict], customer: str = "") -> list[tuple[str, str, int | None]]:
    """THUẦN: items = [{thread_id, amount, text}] → [(title, body, thread_id)].
    title = "💰 <người> nhận <số tiền>", body = dòng đầu nội dung đơn."""
    who = (actor or "?").strip() or "?"
    items = [it for it in items if int(it.get("amount") or 0) > 0]
    if not items:
        return []
    if len(items) <= MAX_EACH:
        return [(f"💰 {who} nhận {_money(it['amount'])}",
                 _peek(it.get("text", "")) or f"Đơn #{it.get('thread_id')}", it.get("thread_id"))
                for it in items]
    total = sum(int(it["amount"]) for it in items)
    body = f"{len(items)} đơn" + (f" của {customer}" if customer else "")
    return [(f"💰 {who} nhận {_money(total)}", body, items[0].get("thread_id"))]


def _display(conn, actor: str) -> str:
    """username web → tên hiển thị (web_users); mã Telegram → USER_NAMES; còn lại giữ nguyên."""
    a = str(actor or "").strip()
    if a.isdigit():
        try:
            from bot_core.config import USER_NAMES
            return USER_NAMES.get(a, a)
        except Exception:  # noqa: BLE001
            return a
    try:
        row = conn.execute("SELECT display_name FROM web_users WHERE username = ?", (a.lower(),)).fetchone()
        if row and row[0]:
            return str(row[0])
    except Exception:  # noqa: BLE001
        pass
    return a


def _texts(thread_ids: list[int], actor: str = "") -> dict:
    from order_store.serialization import get_order_by_thread_id
    conn = get_connection()
    try:
        out: dict = {"_actor": _display(conn, actor)}
        for tid in thread_ids:
            o = get_order_by_thread_id(conn, int(tid)) or {}
            out[int(tid)] = o.get("text") or o.get("text_raw") or ""
            out[-int(tid)] = o.get("customer_name") or ""   # tên khách (khoá âm) cho push tổng
        return out
    finally:
        conn.close()


async def _run(actor: str, allocations: list[tuple[int, int]], payment_id: str | None) -> None:
    try:
        tids = [int(t) for t, _ in allocations]
        texts = await asyncio.to_thread(_texts, tids, actor)
        items = [{"thread_id": t, "amount": a, "text": texts.get(int(t), "")} for t, a in allocations]
        from server_app.notify import push_bg
        for title, body, tid in build_payment_notifs(texts.get("_actor") or actor, items,
                                                     texts.get(-tids[0], "") if tids else ""):
            data = {"type": "payment", "thread_id": str(tid) if tid else ""}
            if payment_id and len(allocations) == 1:
                data["payment_id"] = str(payment_id)
            push_bg(title, body, data)
    except Exception as e:  # noqa: BLE001 — push là phụ, không làm hỏng thu tiền
        log.warning("payment push lỗi: %s", e)


def notify_payment_bg(actor: str, allocations: list[tuple[int, int]], payment_id: str | None = None) -> None:
    """Lên lịch push (nền). allocations = [(thread_id, số tiền)] ĐÃ GHI thành công."""
    if not allocations:
        return
    from server_app.tasks import spawn_tracked
    spawn_tracked("notify.payment", _run(actor, list(allocations), payment_id))
