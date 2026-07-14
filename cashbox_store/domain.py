"""Máy trạng thái TIỀN của một đơn → biến động két (THUẦN, không IO — unit-tested).

Mô hình: tổng tiền đơn T nằm ở đúng 1 chỗ tại mọi thời điểm — bắt đầu ở KHÁCH
(EXTERNAL), giao hàng xong → két người giao (COD), nộp tiền → két văn phòng
(tra_tien_mat) / két khách nợ (ký toa hoặc không) / két chưa rõ (không note,
skip), tạo payment → rút từ chỗ hiện tại sang két người tạo (CK → két ngân
hàng). Mọi biến động là cặp src→dst cân bằng ⇒ tổng bảo toàn theo cấu trúc.
Kết nối: cashbox_store.identity (canon), cashbox_store.service (ráp + IO);
tests/test_cashbox_domain.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

EXTERNAL = "external"          # tiền còn ở khách — nguồn/đích ngoài hệ thống két
SINCE = "2026-06-01"           # chỉ xét đơn từ mốc này (khớp mirror task/kho)
_VN = timezone(timedelta(hours=7))
_NOP_DEADLINE_HOUR = 17        # hạn nộp 17:00 VN cùng ngày giao

# outcome nộp tiền → két đích (note đã split(";")[0])
_NOP_DEST = {
    "tra_tien_mat": "office",
    "co_ky_toa": "debt",
    "khong_ky_toa": "debt",
    "chieu_lay_tien": "debt",      # legacy done=True với note này = nợ tạm
    "chiều lấy tiền": "debt",
    "chieu lay tien": "debt",
    "skip": "unknown",
}


def _ts(v: Any) -> float:
    """ISO / epoch s / epoch ms → epoch giây (float); hỏng → 0.0."""
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        x = float(v)
        return x / 1000.0 if x > 1e12 else x
    s = str(v)
    try:
        x = float(s)
        return x / 1000.0 if x > 1e12 else x
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def nop_outcome(note: Any) -> str:
    """note của nop_tien → mã kết quả ('' nếu không note)."""
    return str(note or "").split(";")[0].strip()


def is_overdue(hold_since: float, now: float) -> bool:
    """Giữ tiền quá hạn nộp? Hạn = 17:00 VN ngày bắt đầu giữ."""
    if not hold_since:
        return False
    d = datetime.fromtimestamp(hold_since, _VN)
    deadline = d.replace(hour=_NOP_DEADLINE_HOUR, minute=0, second=0, microsecond=0)
    if d.hour >= _NOP_DEADLINE_HOUR:   # giao sau 17:00 → hạn 17:00 hôm sau
        deadline += timedelta(days=1)
    return now > deadline.timestamp()


def derive_order_movements(data: dict, total: int, canon: Callable[[Any], str]) -> dict:
    """Đơn (blob dict) + tổng tiền T → biến động két + vị trí phần còn lại.

    Trả {"moves": [movement], "loc": khoá két hiện giữ phần chưa thu (hoặc
    EXTERNAL), "remaining": int, "hold_since": epoch, "hold_note": str}.
    Movement = {ts, at, src, dst, amount, reason, actor, thread_id}.
    """
    tid = data.get("thread_id")
    order_ts = _ts(data.get("created")) or float(tid or 0)
    task_status = data.get("task_status")
    if not isinstance(task_status, dict):
        task_status = {}
    events: list[tuple[float, int, str, dict]] = []

    giao = task_status.get("giao_hang")
    if not isinstance(giao, dict):
        giao = {}
    if giao.get("done") and not giao.get("skip"):
        events.append((_ts(giao.get("at")) or order_ts, 0, "giao", giao))

    payments = data.get("payments")
    for p in (payments if isinstance(payments, list) else []):
        if not isinstance(p, dict):
            continue
        try:
            amount = int(round(float(p.get("amount") or 0)))
        except (TypeError, ValueError):
            amount = 0
        if amount <= 0:
            continue
        pts = _ts(p.get("created_at") or p.get("createdAt")) or (order_ts + 1.0)
        events.append((pts, 1, "payment", {"amount": amount, "by": p.get("createdBy"),
                                           "method": p.get("method")}))

    nop = task_status.get("nop_tien")
    if not isinstance(nop, dict):
        nop = {}
    if nop.get("done"):
        outcome = "skip" if nop.get("skip") else nop_outcome(nop.get("note"))
        events.append((_ts(nop.get("at")) or order_ts, 2, "nop",
                       {"by": nop.get("by"), "outcome": outcome}))

    events.sort(key=lambda e: (e[0], e[1]))

    moves: list[dict] = []
    paid = 0
    loc = EXTERNAL
    hold_since = 0.0
    hold_note = ""

    def _move(ts: float, src: str, dst: str, amount: int, reason: str, actor: Any) -> None:
        if amount > 0 and src != dst:
            moves.append({"ts": ts, "src": src, "dst": dst, "amount": amount,
                          "reason": reason, "actor": actor, "thread_id": tid})

    for ts, _prio, kind, ev in events:
        if kind == "giao":
            if loc == EXTERNAL:
                amt = total - paid
                if amt > 0:
                    dst = canon(ev.get("by"))
                    _move(ts, EXTERNAL, dst, amt, "giao_hang", ev.get("by"))
                    loc, hold_since = dst, ts
        elif kind == "payment":
            a = ev["amount"]
            dst = "bank" if str(ev.get("method") or "").lower() == "transfer" else canon(ev.get("by"))
            reason = "payment_ck" if dst == "bank" else "payment"
            if loc != EXTERNAL:
                take = max(0, min(a, total - paid))
                _move(ts, loc, dst, take, reason, ev.get("by"))
                if a - take > 0:   # thu vượt phần đơn này còn — tiền mới từ khách
                    _move(ts, EXTERNAL, dst, a - take, reason, ev.get("by"))
            else:
                _move(ts, EXTERNAL, dst, a, reason, ev.get("by"))
            paid += a
        elif kind == "nop":
            amt = total - paid
            dst = _NOP_DEST.get(ev["outcome"], "unknown")
            if amt > 0:
                _move(ts, loc, dst, amt, f"nop_tien:{ev['outcome'] or 'khong_ro'}", ev.get("by"))
                loc, hold_since = dst, ts
                hold_note = ev["outcome"]

    remaining = max(0, total - paid)
    if remaining <= 0:
        loc = EXTERNAL   # đã thu đủ — không còn phần "đang nằm két" của đơn này
    if loc == EXTERNAL:
        hold_since, hold_note = 0.0, ""
    elif not nop.get("done") and nop_outcome(nop.get("note")) == "chieu_lay_tien":
        hold_note = "chieu_lay_tien"
    return {"moves": moves, "loc": loc, "remaining": remaining,
            "hold_since": hold_since, "hold_note": hold_note}


def aggregate_balances(moves: list[dict]) -> dict[str, int]:
    """Cộng dồn biến động → số dư từng két (gồm cả EXTERNAL âm/dương).

    Bất biến bảo toàn: sum(kết quả.values()) == 0 với MỌI danh sách movement.
    """
    bal: dict[str, int] = {}
    for m in moves:
        bal[m["src"]] = bal.get(m["src"], 0) - m["amount"]
        bal[m["dst"]] = bal.get(m["dst"], 0) + m["amount"]
    return bal
