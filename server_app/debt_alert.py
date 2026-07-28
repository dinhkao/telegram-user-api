"""Cảnh báo CÔNG NỢ QUÁ HẠN — khách đã nhận hàng nhưng chưa trả tiền quá N ngày.

Ví dụ 1 dòng cảnh báo: "Loan Phú đang có công nợ đã 3 ngày chưa thanh toán từ 3
đơn hàng · 4.200.000đ".

Luật (unit-test ở tests/test_debt_alert.py):
  • Đơn tính vào cảnh báo = đơn CÒN NỢ theo đúng luật trang thu tiền
    (`order_api_collect._owing_remaining`: bỏ `bo_theo_doi_no`, tổng > 0, còn
    thiếu > 0) VÀ **không bị ẩn khỏi thu tiền** (`bypass_debt`).
  • Phải ĐÃ GIAO XONG — mốc đếm ngày = lúc task `giao_hang` done (`task_status
    .giao_hang.at`), đơn cũ chỉ có cờ mirror `giao` thì lấy `created`.
  • Số ngày = chênh lệch NGÀY theo giờ VN (giao hôm qua = 1 ngày), gộp theo khách:
    `days` = đơn quá hạn LÂU NHẤT, `order_count`/`total` = các đơn ĐÃ quá ngưỡng.
  • CHỈ đơn tạo TỪ `DEBT_ALERT_SINCE` (mặc định 2026-07-01, theo NGÀY VN) — nợ cũ
    trước mốc không nhắc (giống CASHBOX_SINCE của hệ két). Đơn thiếu/hỏng
    `created` coi như đơn CŨ → bỏ qua.

Đọc: GET /api/debt-alerts?days=N (văn phòng) — trang webapp #/no-qua-han; bộ nhắc
mỗi ngày ở server_app/debt_alert_daily.py. Nối: order_api_collect, customer_feed
(_ts_key), order_db.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone

from aiohttp import web

from order_db import _get_connection
from server_app.customer_feed import _ts_key
from server_app.order_api_collect import _is_hidden, _owing_remaining
from server_app.order_api_common import is_office_request

log = logging.getLogger("server")

_VN_TZ = timezone(timedelta(hours=7))
# Ngưỡng mặc định: nợ từ 1 ngày (giao hôm qua, hôm nay chưa trả) là đã cảnh báo.
DEFAULT_MIN_DAYS = 1


def _parse_date(s: str | None) -> date | None:
    try:
        return date.fromisoformat((s or "").strip())
    except (AttributeError, TypeError, ValueError):
        return None


# Chỉ nhắc nợ của đơn tạo TỪ mốc này (ngày VN) — nợ cũ trước đó không đụng tới.
SINCE = _parse_date(os.getenv("DEBT_ALERT_SINCE")) or date(2026, 7, 1)


def today_vn() -> date:
    """Hôm nay theo giờ VN (server có thể chạy TZ khác)."""
    return datetime.now(_VN_TZ).date()


def delivered_ts(data: dict) -> float | None:
    """Mốc GIAO XONG của đơn (epoch giây) — None nếu chưa giao / đã skip.

    Ưu tiên `task_status.giao_hang.at`; đơn cũ (flow 1) chỉ có cờ mirror `giao`
    thì lùi về `created` để vẫn đếm được ngày nợ."""
    status = (data.get("task_status") or {}).get("giao_hang") or {}
    if status.get("done") and not status.get("skip"):
        return _ts_key(status.get("at")) or _ts_key(data.get("created")) or None
    if status:
        return None   # có task giao hàng nhưng chưa done / đã skip
    if data.get("giao") is True or data.get("giao_hang") is True:
        return _ts_key(data.get("created")) or None
    return None


def created_date_vn(data: dict) -> date | None:
    """Ngày TẠO ĐƠN theo giờ VN — None nếu đơn không có/hỏng `created`."""
    ts = _ts_key(data.get("created"))
    if not ts:
        return None
    return datetime.fromtimestamp(ts, _VN_TZ).date()


def days_overdue(ts: float, today: date | None = None) -> int:
    """Số NGÀY (giờ VN) từ mốc `ts` tới hôm nay — giao hôm nay = 0, hôm qua = 1."""
    d = datetime.fromtimestamp(ts, _VN_TZ).date()
    return ((today or today_vn()) - d).days


def money_vn(n: int | float) -> str:
    """123456 → '123.456đ' (định dạng tiền VN cho nội dung thông báo)."""
    return f"{int(n):,}".replace(",", ".") + "đ"


def alert_line(a: dict) -> str:
    """Câu cảnh báo 1 dòng cho 1 khách (nội dung thông báo trong app + push)."""
    return (f"{a['name']} đang có công nợ đã {a['days']} ngày chưa thanh toán "
            f"từ {a['order_count']} đơn hàng · {money_vn(a['total'])}")


def _customers(conn) -> dict[str, dict]:
    """Bản đồ khách (tên + kh_id KiotViet) — quét nhanh trong bộ nhớ."""
    out: dict[str, dict] = {}
    for fk, jt in conn.execute("SELECT firebase_key, json FROM customers WHERE deleted_at IS NULL"):
        try:
            cd = json.loads(jt)
        except (TypeError, ValueError):
            continue
        out[str(fk)] = {"name": cd.get("name") or cd.get("ten") or str(fk), "kh_id": cd.get("kh_id")}
    return out


def compute_debt_alerts(conn, min_days: int = DEFAULT_MIN_DAYS, today: date | None = None,
                        since: date | None = None) -> dict:
    """Khách có đơn ĐÃ GIAO còn nợ quá `min_days` ngày → {alerts, count, total}.

    Chỉ xét đơn TẠO TỪ `since` (mặc định `SINCE` = 2026-07-01) — nợ cũ hơn không
    nhắc. `alerts` xếp nợ lâu nhất trước (cùng số ngày thì tiền nhiều trước). Mỗi
    dòng: key/name/days/order_count/total/source_thread_id (đơn quá hạn CŨ NHẤT —
    mở thẳng trang thu tiền)/blocked (khách chưa liên kết KiotViet)."""
    day = today or today_vn()
    start = since or SINCE
    min_days = max(0, int(min_days))
    agg: dict[str, dict] = {}
    for r in conn.execute("SELECT thread_id, json FROM orders WHERE deleted_at IS NULL AND json IS NOT NULL"):
        thread_id = r["thread_id"]
        if thread_id is None:
            continue
        try:
            data = json.loads(r["json"])
        except (TypeError, ValueError):
            continue
        key = data.get("khach_hang_id") or data.get("khID")
        if not key:
            continue
        created = created_date_vn(data)
        if created is None or created < start:
            continue   # nợ cũ trước mốc / đơn không rõ ngày tạo → không nhắc
        rem = _owing_remaining(data)
        if rem is None or _is_hidden(data):
            continue
        ts = delivered_ts(data)
        if ts is None:
            continue
        days = days_overdue(ts, day)
        if days < min_days:
            continue
        e = agg.setdefault(str(key), {
            "days": 0, "order_count": 0, "total": 0,
            "source_thread_id": int(thread_id), "oldest": ts,
        })
        e["order_count"] += 1
        e["total"] += rem
        if days > e["days"]:
            e["days"] = days
        if ts < e["oldest"]:
            e["oldest"] = ts
            e["source_thread_id"] = int(thread_id)
    custs = _customers(conn)
    alerts: list[dict] = []
    for key, e in agg.items():
        c = custs.get(key) or {}
        alerts.append({
            "key": key,
            "name": c.get("name") or key,
            "days": e["days"],
            "order_count": e["order_count"],
            "total": e["total"],
            "source_thread_id": e["source_thread_id"],
            "blocked": not c.get("kh_id"),
        })
    alerts.sort(key=lambda a: (-a["days"], -a["total"]))
    return {
        "alerts": alerts,
        "count": len(alerts),
        "total": sum(a["total"] for a in alerts),
        "min_days": min_days,
        "since": start.isoformat(),
    }


async def debt_alerts_handler(request: web.Request):
    """GET /api/debt-alerts?days=N — khách nợ quá hạn (văn phòng)."""
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới xem được công nợ"}, status=403)
    try:
        min_days = int(request.query.get("days", DEFAULT_MIN_DAYS))
    except (TypeError, ValueError):
        min_days = DEFAULT_MIN_DAYS

    def _run():
        conn = _get_connection()
        try:
            return compute_debt_alerts(conn, min_days)
        finally:
            conn.close()

    res = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, **res})
