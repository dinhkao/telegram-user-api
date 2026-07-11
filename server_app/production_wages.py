"""Dashboard TIỀN CÔNG thợ theo ngày — GET /api/production/wages?from=&to=.

NHẠY CẢM (lương): CHỈ role văn phòng (admin/van_phong) được xem — chặn ngay ở
server (đọc token qua web_auth middleware → tra role web_users), KHÔNG phụ thuộc cờ
WEB_AUTH_ENABLED. Không có token / không phải văn phòng → 403.

Tiền 1 thợ / 1 ngày = Σ (số cây SP đó thợ làm × đơn giá lương SP). Số cây lấy từ
production_report_rows (tong_calc, gộp mọi phiếu trong ngày); đơn giá từ
production_store.wages. Khớp mã HIỆN HÀNH (join products theo product_id → đổi mã
vẫn đúng). Đọc-only. Nối: user_store (role), production_report_rows, products.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from aiohttp import web

from order_db import _get_connection
from production_store.wages import wage_per_cay

_VN = timezone(timedelta(hours=7))
_DEFAULT_DAYS = 45


def office_user(request: web.Request) -> dict | None:
    """User văn phòng (admin/van_phong) từ token đã giải; None nếu thiếu/không đủ quyền."""
    from user_store import get_user, is_office
    username = request.get("web_user")
    if not username:
        return None
    row = get_user(username)
    return row if row and is_office(row.get("role")) else None


def _today_vn() -> str:
    return datetime.now(_VN).strftime("%Y-%m-%d")


def compute_wages(dfrom: str | None, dto: str | None) -> dict:
    if not dto:
        dto = _today_vn()
    if not dfrom:
        try:
            base = datetime.strptime(dto, "%Y-%m-%d")
        except ValueError:
            base = datetime.now(_VN).replace(tzinfo=None)
            dto = base.strftime("%Y-%m-%d")
        dfrom = (base - timedelta(days=_DEFAULT_DAYS - 1)).strftime("%Y-%m-%d")

    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT t.report_ymd AS ymd, COALESCE(w.name, t.worker_name) AS worker, "
            "COALESCE(pr.code, t.product_code) AS code, ROUND(SUM(t.tong_calc),1) AS cay "
            "FROM production_report_rows t "
            "LEFT JOIN production_workers w ON w.id = t.worker_id "
            "LEFT JOIN products pr ON pr.id = t.product_id "
            "WHERE t.tong_calc > 0 AND t.report_ymd IS NOT NULL "
            "  AND t.report_ymd >= ? AND t.report_ymd <= ? "
            "GROUP BY t.report_ymd, worker, code "
            "ORDER BY t.report_ymd DESC",
            (dfrom, dto),
        ).fetchall()
    finally:
        conn.close()

    days: dict = {}          # ymd → {money, cay, workers: {name → {money, cay, items:[]}}}
    missing: set = set()
    for r in rows:
        ymd, worker, code, cay = r["ymd"], (r["worker"] or "?"), (r["code"] or ""), float(r["cay"] or 0)
        wage = wage_per_cay(code)
        if wage <= 0:
            missing.add(code)
        money = round(cay * wage)
        d = days.setdefault(ymd, {"ymd": ymd, "money": 0, "cay": 0.0, "workers": {}})
        wk = d["workers"].setdefault(worker, {"name": worker, "money": 0, "cay": 0.0, "items": []})
        wk["items"].append({"code": code, "cay": cay, "wage": wage, "money": money})
        wk["money"] += money
        wk["cay"] = round(wk["cay"] + cay, 1)
        d["money"] += money
        d["cay"] = round(d["cay"] + cay, 1)

    day_list = []
    for ymd in sorted(days, reverse=True):
        d = days[ymd]
        workers = sorted(d["workers"].values(), key=lambda x: -x["money"])
        for wk in workers:
            wk["items"].sort(key=lambda x: -x["money"])
        day_list.append({"ymd": ymd, "money": d["money"], "cay": d["cay"], "workers": workers})

    return {
        "ok": True, "from": dfrom, "to": dto,
        "days": day_list,
        "totals": {"money": sum(d["money"] for d in day_list), "cay": round(sum(d["cay"] for d in day_list), 1)},
        "missing_wage": sorted(c for c in missing if c),
    }


async def wages_dashboard_handler(request: web.Request):
    if not office_user(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng được xem tiền lương."}, status=403)
    dfrom = request.query.get("from") or None
    dto = request.query.get("to") or None
    data = await asyncio.to_thread(compute_wages, dfrom, dto)
    return web.json_response(data)
