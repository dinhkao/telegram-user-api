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


def is_office_username(username: str | None) -> bool:
    """username có phải văn phòng (admin/van_phong) không — tra role web_users."""
    from user_store import get_user, is_office
    if not username:
        return False
    row = get_user(username)
    return bool(row and is_office(row.get("role")))


def office_user(request: web.Request) -> dict | None:
    """User văn phòng (admin/van_phong) từ token đã giải; None nếu thiếu/không đủ quyền."""
    from user_store import get_user
    username = request.get("web_user")
    if not username or not is_office_username(username):
        return None
    return get_user(username)


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
        from production_store.allowances import allowances_by_day_worker
        allow = allowances_by_day_worker(conn, dfrom, dto)   # {(ymd, worker): Σ phụ cấp}
    finally:
        conn.close()

    days: dict = {}          # ymd → {money, cay, allowance, workers: {name → {money, cay, allowance, items:[]}}}
    missing: set = set()
    for r in rows:
        ymd, worker, code, cay = r["ymd"], (r["worker"] or "?"), (r["code"] or ""), float(r["cay"] or 0)
        wage = wage_per_cay(code)
        if wage <= 0:
            missing.add(code)
        money = round(cay * wage)
        d = days.setdefault(ymd, {"ymd": ymd, "money": 0, "cay": 0.0, "allowance": 0, "workers": {}})
        wk = d["workers"].setdefault(worker, {"name": worker, "money": 0, "cay": 0.0, "allowance": 0, "items": []})
        wk["items"].append({"code": code, "cay": cay, "wage": wage, "money": money})
        wk["money"] += money
        wk["cay"] = round(wk["cay"] + cay, 1)
        d["money"] += money
        d["cay"] = round(d["cay"] + cay, 1)

    # cộng PHỤ CẤP theo (ngày, thợ) — cả vào tiền thợ lẫn tổng ngày (tạo thợ nếu chỉ có phụ cấp)
    for (ymd, worker), amt in allow.items():
        amt = round(amt)
        if amt == 0:
            continue
        d = days.setdefault(ymd, {"ymd": ymd, "money": 0, "cay": 0.0, "allowance": 0, "workers": {}})
        wk = d["workers"].setdefault(worker, {"name": worker, "money": 0, "cay": 0.0, "allowance": 0, "items": []})
        wk["allowance"] += amt
        wk["money"] += amt
        d["allowance"] += amt
        d["money"] += amt

    day_list = []
    for ymd in sorted(days, reverse=True):
        d = days[ymd]
        workers = sorted(d["workers"].values(), key=lambda x: -x["money"])
        for wk in workers:
            wk["items"].sort(key=lambda x: -x["money"])
        day_list.append({"ymd": ymd, "money": d["money"], "cay": d["cay"],
                         "allowance": d.get("allowance", 0), "workers": workers})

    return {
        "ok": True, "from": dfrom, "to": dto,
        "days": day_list,
        "totals": {"money": sum(d["money"] for d in day_list), "cay": round(sum(d["cay"] for d in day_list), 1),
                   "allowance": sum(d.get("allowance", 0) for d in day_list)},
        "missing_wage": sorted(c for c in missing if c),
    }


async def wages_dashboard_handler(request: web.Request):
    if not office_user(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng được xem tiền lương."}, status=403)
    dfrom = request.query.get("from") or None
    dto = request.query.get("to") or None
    data = await asyncio.to_thread(compute_wages, dfrom, dto)
    return web.json_response(data)


# ── Tiền công + PHỤ CẤP theo PHIẾU (office) — cho khối tiền ở chi tiết phiếu SX ──
def _phieu_wages(thread_id: int) -> dict:
    from production_store.allowances import get_allowances
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT COALESCE(pr.code, t.product_code) FROM production_report_rows t "
            "LEFT JOIN products pr ON pr.id = t.product_id WHERE t.thread_id = ? LIMIT 1",
            (thread_id,),
        ).fetchone()
        code = (row[0] if row else "") or ""
        return {"ok": True, "thread_id": thread_id, "product_code": code,
                "wage": wage_per_cay(code), "allowances": get_allowances(conn, thread_id)}
    finally:
        conn.close()


async def phieu_wages_handler(request: web.Request):
    if not office_user(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng"}, status=403)
    try:
        tid = int(request.match_info.get("thread_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    data = await asyncio.to_thread(_phieu_wages, tid)
    return web.json_response(data)


async def set_allowance_handler(request: web.Request):
    """Đặt/sửa phụ cấp 1 (phiếu, thợ) — CHỈ văn phòng."""
    user = office_user(request)
    if not user:
        return web.json_response({"ok": False, "error": "Chỉ văn phòng"}, status=403)
    try:
        tid = int(request.match_info.get("thread_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    body = await request.json()
    worker = str(body.get("worker_name") or "").strip()
    if not worker:
        return web.json_response({"ok": False, "error": "thiếu tên thợ"}, status=400)
    try:
        amount = float(body.get("amount") or 0)
    except (ValueError, TypeError):
        amount = 0.0

    def _run():
        from production_store.allowances import set_allowance
        conn = _get_connection()
        try:
            set_allowance(conn, tid, worker, amount, by=str(user.get("username") or ""))
        finally:
            conn.close()

    await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "worker_name": worker, "amount": max(0.0, amount)})
