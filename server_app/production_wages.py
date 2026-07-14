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
            "SELECT t.thread_id AS tid, t.report_ymd AS ymd, t.worker_name AS wname, "
            "COALESCE(w.name, t.worker_name) AS worker, "
            "COALESCE(pr.code, t.product_code) AS code, ROUND(SUM(t.tong_calc),1) AS cay, "
            # cây TÍNH TIỀN = chỉ từ dòng KHÔNG có giờ (dòng giờ trả theo giờ, cây của
            # dòng đó không tính tiền SP — GROUP BY gộp dòng nên phải tách ngay ở SUM)
            "ROUND(SUM(CASE WHEN COALESCE(t.so_gio,0) > 0 THEN 0 ELSE t.tong_calc END),1) AS cay_piece, "
            "SUM(t.so_gio) AS gio, COALESCE(w.hourly_rate, 0) AS hrate, "
            "s.luong_1sp AS slip_wage, s.kind AS slip_kind "
            "FROM production_report_rows t "
            "LEFT JOIN production_workers w ON w.id = t.worker_id "
            "LEFT JOIN products pr ON pr.id = t.product_id "
            "LEFT JOIN production_slips s ON s.thread_id = t.thread_id "
            "WHERE t.report_ymd IS NOT NULL "   # BỎ lọc tong>0 → hiện cả thợ làm 0 SP
            "  AND t.report_ymd >= ? AND t.report_ymd <= ? "
            # GROUP BY biểu thức đầy đủ — tên trần "code" resolve về pr.code (NULL khi
            # thiếu product_id) → các mã SP của dòng cổ bị gộp nhầm làm một.
            # Tách theo thread_id để lấy ĐƠN GIÁ CHỐT THEO PHIẾU (luong_1sp).
            "GROUP BY t.thread_id, t.worker_name, COALESCE(w.name, t.worker_name), "
            "         COALESCE(pr.code, t.product_code) "
            "ORDER BY t.report_ymd DESC",
            (dfrom, dto),
        ).fetchall()
        # PHỤ CẤP theo (phiếu, thợ snapshot) của các phiếu trong khoảng
        tids = sorted({r["tid"] for r in rows})
        allow: dict = {}
        if tids:
            qs = ",".join("?" * len(tids))
            for a in conn.execute(
                f"SELECT thread_id, worker_name, amount FROM production_allowances WHERE thread_id IN ({qs})",
                tids,
            ).fetchall():
                allow[(a["thread_id"], a["worker_name"])] = float(a["amount"] or 0)
    finally:
        conn.close()

    def _mk_day(ymd):
        return days.setdefault(ymd, {"ymd": ymd, "money": 0, "cay": 0.0, "allowance": 0, "workers": {}})

    def _mk_wk(d, worker):
        return d["workers"].setdefault(worker, {"name": worker, "money": 0, "cay": 0.0, "allowance": 0, "items": []})

    days: dict = {}          # ymd → {money, cay, allowance, workers: {name → {money, cay, allowance, items:[]}}}
    missing: set = set()
    missing_rate: set = set()   # thợ có GIỜ nhưng chưa đặt tiền 1 giờ
    allow_used: set = set()  # (tid, wname) đã cộng phụ cấp — đúng 1 lần / (phiếu, thợ)
    tid_ymd: dict = {}       # tid → ymd (cho phụ cấp mồ côi)
    def _add_item(wk, *, code, wage, hourly, cay=0.0, gio=0.0, hrate=0.0, piece=0, a=0):
        """1 dòng hiển thị theo (mã, đơn giá, tính-giờ) — cây và giờ tách dòng riêng."""
        it = next((x for x in wk["items"] if x["code"] == code and x["wage"] == wage
                   and bool(x.get("gio")) == hourly), None)
        if it is None:
            it = {"code": code, "cay": 0.0, "wage": wage, "piece": 0, "allowance": 0, "money": 0,
                  "gio": 0.0, "hourly_rate": hrate if hourly else 0}
            wk["items"].append(it)
        it["cay"] = round(it["cay"] + cay, 1)
        it["gio"] = round(it["gio"] + gio, 2)
        it["piece"] += piece
        it["allowance"] += a
        it["money"] += piece + a

    for r in rows:
        tid, ymd, wname = r["tid"], r["ymd"], r["wname"]
        worker, code, cay = (r["worker"] or "?"), (r["code"] or ""), float(r["cay"] or 0)
        cay_piece = float(r["cay_piece"] or 0)
        # GIỜ chỉ tính ở phiếu SẢN XUẤT (gate UI có thể bị lách qua Telegram paste)
        hourly_ok = (r["slip_kind"] or "san_xuat") != "dong_goi"
        gio = float(r["gio"] or 0) if hourly_ok else 0.0
        hrate = float(r["hrate"] or 0)
        tid_ymd.setdefault(tid, ymd)
        d = _mk_day(ymd)
        # HIỆN MỌI dòng SP thợ có mặt trong phiếu — kể cả làm 0 cây (0đ). Thợ luôn được tạo.
        wk = _mk_wk(d, worker)
        # đơn giá CHỐT theo phiếu; chưa chốt (NULL) → bảng lương hiện tại
        wage = float(r["slip_wage"]) if r["slip_wage"] is not None else wage_per_cay(code)
        # Tiền = cây (dòng KHÔNG giờ) × đơn giá SP + giờ × tiền-1-giờ của thợ.
        # Thợ vừa làm SP vừa làm giờ trong 1 phiếu → nhận CẢ HAI (không nuốt nhau).
        piece_sp = round(cay_piece * wage)
        piece_gio = round(gio * hrate)
        if cay_piece > 0 and wage <= 0:   # chỉ cảnh báo thiếu đơn giá khi thực sự có sản lượng
            missing.add(code)
        if gio > 0 and hrate <= 0:
            missing_rate.add(worker)
        a = 0
        if (tid, wname) not in allow_used:
            a = round(allow.get((tid, wname), 0))
            allow_used.add((tid, wname))
        money = piece_sp + piece_gio + a
        if gio > 0:
            _add_item(wk, code=code, wage=wage, hourly=True, gio=gio, hrate=hrate,
                      piece=piece_gio, a=a if cay_piece <= 0 else 0)
        if cay_piece > 0 or gio <= 0:   # dòng cây (kể cả 0 cây khi không có giờ)
            _add_item(wk, code=code, wage=wage, hourly=False, cay=cay if gio <= 0 else cay_piece,
                      piece=piece_sp, a=a if cay_piece > 0 or gio <= 0 else 0)
        wk["money"] += money
        wk["allowance"] += a
        wk["cay"] = round(wk["cay"] + cay, 1)
        d["money"] += money
        d["allowance"] += a
        d["cay"] = round(d["cay"] + cay, 1)

    # An toàn: phụ cấp mồ côi (thợ có phụ cấp nhưng không có dòng SP trong phiếu) → dòng riêng
    for (tid, wname), amt in allow.items():
        amt = round(amt)
        if amt == 0 or (tid, wname) in allow_used or tid not in tid_ymd:
            continue
        d = _mk_day(tid_ymd[tid])
        wk = _mk_wk(d, wname)
        wk["items"].append({"code": "", "cay": 0, "wage": 0, "piece": 0, "allowance": amt, "money": amt})
        wk["money"] += amt
        wk["allowance"] += amt
        d["money"] += amt
        d["allowance"] += amt

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
        "missing_hour_rate": sorted(missing_rate),   # thợ có giờ nhưng chưa đặt tiền 1 giờ
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
        slip = conn.execute(
            "SELECT sp_name, luong_1sp FROM production_slips WHERE thread_id = ?", (thread_id,)
        ).fetchone()
        if not code and slip:
            code = (slip["sp_name"] or "").strip().upper()
        default_wage = wage_per_cay(code)   # bảng lương hiện tại (tham chiếu)
        slip_wage = slip["luong_1sp"] if slip else None
        wage = float(slip_wage) if slip_wage is not None else default_wage
        # tiền 1 GIỜ theo thợ (SP tính lương giờ) — client tính dòng giờ × rate
        try:
            hourly = {r[0]: float(r[1] or 0) for r in conn.execute(
                "SELECT name, hourly_rate FROM production_workers").fetchall()}
        except Exception:
            hourly = {}
        return {"ok": True, "thread_id": thread_id, "product_code": code,
                "wage": wage, "default_wage": default_wage,
                "custom": slip_wage is not None and float(slip_wage) != default_wage,
                "allowances": get_allowances(conn, thread_id),
                "hourly_rates": hourly}
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


async def set_slip_wage_handler(request: web.Request):
    """Chốt/sửa ĐƠN GIÁ LƯƠNG /1SP của RIÊNG 1 phiếu SX — CHỈ văn phòng.
    luong >= 0 (0 = phiếu không tính tiền); mặc định phiếu đã chốt từ bảng lương lúc gán SP."""
    user = office_user(request)
    if not user:
        return web.json_response({"ok": False, "error": "Chỉ văn phòng"}, status=403)
    try:
        tid = int(request.match_info.get("thread_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    body = await request.json()
    try:
        luong = float(body.get("luong"))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "đơn giá không hợp lệ"}, status=400)
    if luong < 0:
        return web.json_response({"ok": False, "error": "đơn giá phải >= 0"}, status=400)

    def _run():
        from production_store import set_slip_wage
        conn = _get_connection()
        try:
            set_slip_wage(conn, tid, luong)
        finally:
            conn.close()

    await asyncio.to_thread(_run)
    # tiền phiếu này đổi → dashboard tiền công + báo cáo + chi tiết phiếu refetch
    from server_app.realtime import emit_production_changed, emit_productions_changed
    emit_production_changed(tid)
    emit_productions_changed()
    return web.json_response({"ok": True, "thread_id": tid, "luong": luong})


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
