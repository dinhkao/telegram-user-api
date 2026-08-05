"""API BẢNG LƯƠNG THÁNG — CHỈ VĂN PHÒNG. Xem bảng lương 1 tháng (mọi thợ), sửa phụ
cấp/thưởng/mốc lương/TRỪ BHXH theo tháng, ghi nhận/VÔ HIỆU ứng lương + phụ cấp (không
xoá — giữ dòng kèm ai/lúc nào/lý do) + SỬA GHI CHÚ khoản đã ghi (số tiền bất biến). Nối: salary_store +
server_app.production_wages (office gate). Client: webapp/src/pages/MonthlyPayroll.tsx.
"""
from __future__ import annotations

import asyncio
import math
import re

from aiohttp import web

from utils.db import get_connection
from utils.paths import SHARED_DB_PATH
from server_app.production_wages import office_user
import salary_store

_YM = re.compile(r"^\d{4}-\d{2}$")


def _deny(request):
    """None nếu là văn phòng; Response 403 nếu không."""
    if not office_user(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng"}, status=403)
    return None


def _money(v, *, positive: bool = True) -> float | None:
    """Parse tiền an toàn: float() nhận cả 'inf'/'nan' → làm hỏng tổng tháng, phải
    chặn non-finite. positive=True → phải > 0; False → chỉ cần ≥ 0 (0 = xoá).
    Trả None nếu không hợp lệ."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f) or f < 0 or (positive and f == 0):
        return None
    return f


async def payroll_month_handler(request: web.Request):
    """GET /api/payroll/month?ym=YYYY-MM → bảng lương tháng (mọi thợ + tổng)."""
    d = _deny(request)
    if d:
        return d
    ym = (request.query.get("ym") or "").strip()
    if not _YM.match(ym):
        return web.json_response({"ok": False, "error": "ym phải dạng YYYY-MM"}, status=400)

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            return salary_store.compute_month_payroll(conn, ym)
        finally:
            conn.close()

    data = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, **data})


async def payroll_advances_handler(request: web.Request):
    """GET /api/payroll/advances?ym=YYYY-MM[&worker_id=] → các lần ứng. Không có
    worker_id = MỌI thợ trong tháng (cho trang nhập ứng lương)."""
    d = _deny(request)
    if d:
        return d
    ym = (request.query.get("ym") or "").strip()
    if not _YM.match(ym):
        return web.json_response({"ok": False, "error": "ym phải dạng YYYY-MM"}, status=400)
    wq = request.query.get("worker_id")
    worker_id = None
    if wq not in (None, ""):
        try:
            worker_id = int(wq)
        except (ValueError, TypeError):
            return web.json_response({"ok": False, "error": "worker_id không hợp lệ"}, status=400)

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            return salary_store.list_advances(conn, ym, worker_id)
        finally:
            conn.close()

    rows = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "advances": rows})


async def payroll_adjust_handler(request: web.Request):
    """POST /api/payroll/adjust
    {ym, worker_id, thuong?, note?, weekly?, thuong_cc?, thuong_vs?, cho_hang?,
     monthly_salary?, bhxh?}
    — sửa thưởng/ghi chú/nhận-lương-tuần/2 cờ THƯỞNG (chuyên cần, vệ sinh)/MỐC LƯƠNG/
    TRỪ BHXH theo tháng (field vắng = giữ nguyên). thuong_cc/thuong_vs là cờ bật-tắt,
    số tiền tính live (salary_store/bonus.py) và KHÔNG kế thừa sang tháng sau.
    monthly_salary = mốc lương tháng của thợ lương thời gian, ghi vào ĐÚNG tháng ym
    (0 = bỏ mốc riêng tháng này → kế thừa mốc gần nhất trước đó); sửa mốc KHÔNG tính
    lại tháng cũ — xem salary_store/moc.py.
    bhxh = số TRỪ BHXH của tháng ym, cùng luật kế thừa nhưng 0 KHÁC "bỏ đặt riêng":
    số ≥ 0 = đặt riêng tháng này (0 = từ tháng này thôi trừ), null = bỏ đặt riêng →
    kế thừa lại bản trước (xem salary_store/bhxh.py). Phụ cấp = nhiều khoản, dùng
    /api/payroll/allowance."""
    d = _deny(request)
    if d:
        return d
    body = await request.json()
    ym = str(body.get("ym") or "").strip()
    if not _YM.match(ym):
        return web.json_response({"ok": False, "error": "ym phải dạng YYYY-MM"}, status=400)
    try:
        worker_id = int(body.get("worker_id"))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "worker_id không hợp lệ"}, status=400)
    thuong = body.get("thuong")
    if thuong is not None:
        thuong = _money(thuong, positive=False)   # 0 = xoá thưởng; None (vắng) = giữ nguyên
        if thuong is None:
            return web.json_response({"ok": False, "error": "Tiền thưởng không hợp lệ"}, status=400)
    # LƯƠNG CHỜ HÀNG: khoản CỘNG gõ tay của tháng ym (0 = xoá). Vắng field = giữ nguyên.
    cho_hang = body.get("cho_hang")
    if cho_hang is not None:
        cho_hang = _money(cho_hang, positive=False)
        if cho_hang is None:
            return web.json_response({"ok": False, "error": "Tiền lương chờ hàng không hợp lệ"}, status=400)
    moc = body.get("monthly_salary")
    if moc is not None:
        moc = _money(moc, positive=False)   # 0 = bỏ mốc riêng tháng này; None (vắng) = giữ nguyên
        if moc is None:
            return web.json_response({"ok": False, "error": "Mốc lương tháng không hợp lệ"}, status=400)
    # BHXH: phải phân biệt "vắng field" (giữ nguyên) ↔ "gửi null" (bỏ đặt riêng tháng
    # này) ↔ "gửi 0" (đặt riêng = 0) → dùng `in body` chứ KHÔNG dùng .get() is not None.
    has_bhxh = "bhxh" in body
    bhxh = None
    if has_bhxh and body["bhxh"] is not None:
        bhxh = _money(body["bhxh"], positive=False)   # 0 hợp lệ; âm/nan → lỗi
        if bhxh is None:
            return web.json_response({"ok": False, "error": "Số trừ BHXH không hợp lệ"}, status=400)
    by = request.get("web_user") or ""
    has_moc = body.get("monthly_salary") is not None

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            salary_store.ensure_schema(conn)
            if any(body.get(k) is not None for k in ("note", "weekly", "thuong_cc", "thuong_vs")) \
                    or thuong is not None or cho_hang is not None:
                salary_store.set_month_adjust(
                    conn, ym, worker_id,
                    thuong=thuong, note=body.get("note"),
                    weekly=body.get("weekly"),
                    thuong_cc=body.get("thuong_cc"), thuong_vs=body.get("thuong_vs"),
                    cho_hang=cho_hang, by=by,
                )
            if has_moc:   # mốc lương ghi vào ĐÚNG tháng ym (không đụng tháng khác)
                salary_store.set_month_moc(conn, ym, worker_id, moc, by=by)
            if has_bhxh:  # bhxh=None ở đây nghĩa là BỎ đặt riêng tháng này
                salary_store.set_month_bhxh(conn, ym, worker_id, bhxh, by=by)
            return salary_store.compute_month_payroll(conn, ym)
        finally:
            conn.close()

    data = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, **data})


async def payroll_advance_add_handler(request: web.Request):
    """POST /api/payroll/advance {worker_id, ym, amount, adv_date?, note?} — thêm 1 lần ứng."""
    d = _deny(request)
    if d:
        return d
    body = await request.json()
    ym = str(body.get("ym") or "").strip()
    if not _YM.match(ym):
        return web.json_response({"ok": False, "error": "ym phải dạng YYYY-MM"}, status=400)
    try:
        worker_id = int(body.get("worker_id"))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "worker_id / số tiền không hợp lệ"}, status=400)
    amount = _money(body.get("amount"))
    if amount is None:
        return web.json_response({"ok": False, "error": "worker_id / số tiền không hợp lệ"}, status=400)
    by = request.get("web_user") or ""

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            salary_store.add_advance(conn, worker_id, ym, amount,
                                     adv_date=str(body.get("adv_date") or ""),
                                     note=str(body.get("note") or ""), by=by)
            return salary_store.compute_month_payroll(conn, ym)
        finally:
            conn.close()

    try:
        data = await asyncio.to_thread(_run)
    except ValueError as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    return web.json_response({"ok": True, **data})


async def payroll_advance_void_handler(request: web.Request):
    """POST /api/payroll/advance/{id}/void {ym, reason} — VÔ HIỆU 1 lần ứng (không xoá,
    giữ dòng kèm ai/lúc nào/lý do; trả bảng tháng mới)."""
    d = _deny(request)
    if d:
        return d
    try:
        aid = int(request.match_info.get("id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    body = await request.json()
    ym = str(body.get("ym") or "").strip()
    reason = str(body.get("reason") or "").strip()
    if not reason:
        return web.json_response({"ok": False, "error": "Phải nhập lý do vô hiệu"}, status=400)
    by = request.get("web_user") or ""

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            ok = salary_store.void_advance(conn, aid, reason, by=by)
            data = salary_store.compute_month_payroll(conn, ym) if _YM.match(ym) else {}
            return ok, data
        finally:
            conn.close()

    ok, data = await asyncio.to_thread(_run)
    return web.json_response({"ok": ok, **data})


async def _note_edit(request: web.Request, kind: str):
    """Thân chung POST .../{id}/note {ym, note} — sửa GHI CHÚ 1 khoản ứng/phụ cấp
    (số tiền bất biến; khoản đã vô hiệu không sửa). Trả bảng tháng mới như void."""
    d = _deny(request)
    if d:
        return d
    try:
        rid = int(request.match_info.get("id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    body = await request.json()
    ym = str(body.get("ym") or "").strip()
    note = str(body.get("note") or "")
    update = (salary_store.update_advance_note if kind == "advance"
              else salary_store.update_allowance_note)

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            if not update(conn, rid, note):
                return False, {}
            return True, (salary_store.compute_month_payroll(conn, ym) if _YM.match(ym) else {})
        finally:
            conn.close()

    ok, data = await asyncio.to_thread(_run)
    if not ok:
        return web.json_response({"ok": False, "error": "Không sửa được (khoản không tồn tại hoặc đã vô hiệu)"},
                                 status=400)
    return web.json_response({"ok": True, **data})


async def payroll_advance_note_handler(request: web.Request):
    """POST /api/payroll/advance/{id}/note {ym, note} — sửa ghi chú 1 lần ứng."""
    return await _note_edit(request, "advance")


async def payroll_allowance_note_handler(request: web.Request):
    """POST /api/payroll/allowance/{id}/note {ym, note} — sửa ghi chú 1 khoản phụ cấp."""
    return await _note_edit(request, "allowance")


async def payroll_allowances_handler(request: web.Request):
    """GET /api/payroll/allowances?ym=YYYY-MM[&worker_id=] → các khoản phụ cấp."""
    d = _deny(request)
    if d:
        return d
    ym = (request.query.get("ym") or "").strip()
    if not _YM.match(ym):
        return web.json_response({"ok": False, "error": "ym phải dạng YYYY-MM"}, status=400)
    wq = request.query.get("worker_id")
    worker_id = None
    if wq not in (None, ""):
        try:
            worker_id = int(wq)
        except (ValueError, TypeError):
            return web.json_response({"ok": False, "error": "worker_id không hợp lệ"}, status=400)

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            # hỏi 1 thợ → quy luôn khoản có CÔNG THỨC ra tiền theo lương gốc hiện tại
            if worker_id is not None:
                base, cong = _pc_base(conn, ym, worker_id)
                return salary_store.list_allowances(conn, ym, worker_id, base=base, cong=cong)
            return salary_store.list_allowances(conn, ym)
        finally:
            conn.close()

    rows = await asyncio.to_thread(_run)
    return web.json_response({"ok": True, "allowances": rows})


def _pc_base(conn, ym: str, worker_id: int) -> tuple[float, float]:
    """(lương gốc, ngày công) của 1 thợ trong tháng — để quy khoản phụ cấp có CÔNG
    THỨC ra tiền. Gốc: thợ SP → lương sản phẩm · thợ TG → lương theo ngày công."""
    data = salary_store.compute_month_payroll(conn, ym)
    row = next((r for r in data["workers"] if r["worker_id"] == worker_id), None)
    if not row:
        return 0.0, 0.0
    base = row["luong_sp"] if row["wage_type"] == "product" else row["luong_cong"]
    return float(base or 0), float(row.get("cong") or 0)


async def payroll_allowance_add_handler(request: web.Request):
    """POST /api/payroll/allowance {worker_id, ym, amount, note?, calc_kind?, calc_value?}
    — thêm 1 khoản phụ cấp. calc_kind='pct'/'day' + calc_value = CÔNG THỨC (% lương gốc
    / đơn giá 1 ngày công): số tiền được TÍNH LẠI theo lương gốc mỗi lần xem, nên
    amount khi đó chỉ là số chụp lúc nhập và ĐƯỢC PHÉP bằng 0."""
    d = _deny(request)
    if d:
        return d
    body = await request.json()
    ym = str(body.get("ym") or "").strip()
    if not _YM.match(ym):
        return web.json_response({"ok": False, "error": "ym phải dạng YYYY-MM"}, status=400)
    try:
        worker_id = int(body.get("worker_id"))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "worker_id / số tiền không hợp lệ"}, status=400)
    kind = str(body.get("calc_kind") or "").strip() or None
    amount = _money(body.get("amount"), positive=not kind)   # có công thức → cho phép 0
    if amount is None:
        return web.json_response({"ok": False, "error": "worker_id / số tiền không hợp lệ"}, status=400)
    by = request.get("web_user") or ""

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            salary_store.add_allowance(conn, worker_id, ym, amount, note=str(body.get("note") or ""),
                                       by=by, calc_kind=kind, calc_value=body.get("calc_value"))
            return salary_store.compute_month_payroll(conn, ym)
        finally:
            conn.close()

    try:
        data = await asyncio.to_thread(_run)
    except ValueError as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    return web.json_response({"ok": True, **data})


async def payroll_allowance_void_handler(request: web.Request):
    """POST /api/payroll/allowance/{id}/void {ym, reason} — VÔ HIỆU 1 khoản phụ cấp
    (không xoá, giữ dòng kèm ai/lúc nào/lý do)."""
    d = _deny(request)
    if d:
        return d
    try:
        aid = int(request.match_info.get("id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "id không hợp lệ"}, status=400)
    body = await request.json()
    ym = str(body.get("ym") or "").strip()
    reason = str(body.get("reason") or "").strip()
    if not reason:
        return web.json_response({"ok": False, "error": "Phải nhập lý do vô hiệu"}, status=400)
    by = request.get("web_user") or ""

    def _run():
        conn = get_connection(SHARED_DB_PATH)
        try:
            ok = salary_store.void_allowance(conn, aid, reason, by=by)
            data = salary_store.compute_month_payroll(conn, ym) if _YM.match(ym) else {}
            return ok, data
        finally:
            conn.close()

    ok, data = await asyncio.to_thread(_run)
    return web.json_response({"ok": ok, **data})
