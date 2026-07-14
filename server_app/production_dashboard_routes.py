"""API dashboard báo cáo sản xuất — GET /api/production/report-dashboard?from=&to=.

Tổng hợp từ bảng quan hệ production_report_rows (production_store.report_rows.dashboard):
tổng sản lượng, theo thợ, theo ngày, theo sản phẩm. from/to = YYYY-MM-DD (lọc report_ymd).
Client: webapp/src/pages/ProductionDashboard.tsx.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from utils.db import get_connection
from utils.paths import SHARED_DB_PATH
from production_store.report_rows import dashboard, worker_detail


async def production_report_dashboard_handler(request: web.Request):
    dfrom = (request.query.get("from") or "").strip() or None
    dto = (request.query.get("to") or "").strip() or None

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            return dashboard(conn, dfrom, dto)
        finally:
            conn.close()

    data = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, **data})


async def production_worker_report_handler(request: web.Request):
    """Chi tiết 1 thợ — mỗi ngày làm phiếu nào / SP gì / bao nhiêu. TIỀN CÔNG (mỗi phiếu +
    tổng) CHỈ đính kèm khi người xem là VĂN PHÒNG (lương nhạy cảm)."""
    name = (request.match_info.get("name") or "").strip()
    if not name:
        return web.json_response({"ok": False, "error": "thiếu tên thợ"}, status=400)
    dfrom = (request.query.get("from") or "").strip() or None
    dto = (request.query.get("to") or "").strip() or None
    username = request.get("web_user")   # do web_auth middleware giải (đọc DB role ở thread)

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            data = worker_detail(conn, name, dfrom, dto)
            # Tiền công: chỉ văn phòng — mỗi row (= 1 phiếu): tiền SP = tong_calc × đơn giá,
            # cộng PHỤ CẤP của (phiếu, thợ) → money = piece + allowance.
            from server_app.production_wages import is_office_username
            if is_office_username(username):
                from production_store.wages import wage_per_cay
                from production_store.allowances import get_allowances
                acache: dict = {}
                swage: dict = {}   # tid → luong_1sp (đơn giá CHỐT theo phiếu)
                skind: dict = {}   # tid → kind (giờ chỉ tính ở phiếu SẢN XUẤT)
                tids = {r.get("thread_id") for r in data.get("rows", []) if r.get("thread_id")}
                if tids:
                    qs = ",".join("?" * len(tids))
                    for sr in conn.execute(
                        f"SELECT thread_id, luong_1sp, kind FROM production_slips WHERE thread_id IN ({qs})",
                        sorted(tids),
                    ).fetchall():
                        swage[sr["thread_id"]] = sr["luong_1sp"]
                        skind[sr["thread_id"]] = sr["kind"]
                # tiền 1 GIỜ của thợ này (dòng có số giờ → tiền = giờ × rate)
                hrate = 0.0
                try:
                    hr = conn.execute(
                        "SELECT hourly_rate FROM production_workers WHERE name = TRIM(?) COLLATE NOCASE",
                        (name,),
                    ).fetchone()
                    hrate = float(hr[0] or 0) if hr else 0.0
                except Exception:
                    hrate = 0.0
                total_money = 0
                allow_used: set = set()   # phụ cấp cộng ĐÚNG 1 lần / phiếu (thợ có nhiều dòng)
                for r in data.get("rows", []):
                    tid = r.get("thread_id")
                    if tid not in acache:
                        acache[tid] = get_allowances(conn, tid)
                    allow = 0
                    if tid not in allow_used:
                        allow = round(acache[tid].get(name, 0))
                        allow_used.add(tid)
                    gio = float(r.get("so_gio") or 0)
                    if gio > 0 and (skind.get(tid) or "san_xuat") == "dong_goi":
                        gio = 0.0   # giờ chỉ áp dụng phiếu SẢN XUẤT
                    if gio > 0:
                        # SP tính lương THEO GIỜ (cây của dòng giờ không tính tiền SP)
                        piece = round(gio * hrate)
                        r["hourly_rate"] = hrate
                        r["wage"] = 0
                    else:
                        sw = swage.get(tid)
                        w = float(sw) if sw is not None else wage_per_cay(r.get("product_code"))
                        piece = round((r.get("tong_calc") or 0) * w)
                        r["wage"] = w
                    r["piece"] = piece
                    r["allowance"] = allow
                    r["money"] = piece + allow
                    total_money += piece + allow
                data["total_money"] = total_money
                data["can_money"] = True
            else:
                data["can_money"] = False
        finally:
            conn.close()
        return data

    data = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, **data})
