"""PHIẾU LƯƠNG THÁNG in giấy — GET /api/payroll/payslip-html?ym=YYYY-MM&worker_id=N.
CHỈ VĂN PHÒNG (lương nhạy cảm). Mở từ popup/trang hồ sơ lương thợ (#/luong-thang).

Gom dữ liệu 1 thợ trong tháng: dòng bảng lương (salary_store.compute_month_payroll —
NGUỒN SỰ THẬT của tiền, phiếu KHÔNG tính lại), các khoản phụ cấp còn hiệu lực, các lần
ứng, giờ chấm công từng ngày (attendance_store.day_summary) → salary_store.payslip
(thuần) → renderers.phieu_luong_thang (HTML khổ hoá đơn).
Client: webapp/src/api.ts::payslipMonthHtmlUrl.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone, timedelta

from aiohttp import web

from utils.db import get_connection
from utils.paths import SHARED_DB_PATH

_YM = re.compile(r"^\d{4}-\d{2}$")
_VN = timezone(timedelta(hours=7))


def _err(msg: str, status: int) -> web.Response:
    return web.Response(text=f"<h3>{msg}</h3>", content_type="text/html", status=status)


def _collect(ym: str, worker_id: int, username: str | None, today: str):
    """Chạy trong thread: đọc DB → payload phiếu. Trả 'forbidden' nếu không phải văn
    phòng, None nếu tháng đó không có thợ mang mã này."""
    from server_app.production_wages import is_office_username
    import salary_store
    import attendance_store
    from salary_store.payslip import build_payslip

    conn = get_connection(SHARED_DB_PATH)
    try:
        if not is_office_username(username):
            return "forbidden"
        data = salary_store.compute_month_payroll(conn, ym)
        row = next((w for w in data["workers"] if w["worker_id"] == worker_id), None)
        if not row:
            return None
        # Phụ cấp: quy khoản theo CÔNG THỨC ra tiền bằng ĐÚNG gốc dòng bảng lương
        # (thợ SP → lương sản phẩm · thợ TG → lương ngày công) — xem allowance_calc.
        base = row["luong_sp"] if (row.get("wage_type") or "product") == "product" else row["luong_cong"]
        allow = [a for a in salary_store.list_allowances(conn, ym, worker_id,
                                                         base=base, cong=row.get("cong"))
                 if not a.get("voided_at")]
        adv = [a for a in salary_store.list_advances(conn, ym, worker_id) if not a.get("voided_at")]
        attendance_store.ensure_schema(conn)
        times = {d["day"]: (d.get("times") or [])
                 for d in attendance_store.day_summary(conn, ym) if d.get("worker_id") == worker_id}
        return build_payslip(row, allow, adv, times, ym=ym, today_ymd=today)
    finally:
        conn.close()


async def payslip_month_html_handler(request: web.Request):
    ym = (request.query.get("ym") or "").strip()
    if not _YM.match(ym):
        return _err("ym phải dạng YYYY-MM", 400)
    try:
        worker_id = int(request.query.get("worker_id") or "")
    except (TypeError, ValueError):
        return _err("worker_id không hợp lệ", 400)
    username = request.get("web_user")
    today = datetime.now(_VN).strftime("%Y-%m-%d")

    payload = await asyncio.to_thread(_collect, ym, worker_id, username, today)
    if payload == "forbidden":
        return _err("Chỉ văn phòng xem được phiếu lương", 403)
    if payload is None:
        return _err(f"Tháng {ym} không có thợ nào mang mã #{worker_id}", 404)
    from renderers.phieu_luong_thang import generate_payslip_month_html
    return web.Response(text=generate_payslip_month_html(payload), content_type="text/html")
