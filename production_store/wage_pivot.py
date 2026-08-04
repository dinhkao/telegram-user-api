"""PIVOT lương sản phẩm: THỢ theo CỘT, NGÀY theo HÀNG (+ view mở rộng theo PHIẾU SX).

Không tự tính tiền lại — chỉ XOAY BẢNG kết quả của
`production_store.report_slips.compute_range_report` (nguồn sự thật duy nhất của
tiền công: cây × đơn giá CHỐT theo phiếu + tiền giờ + phụ cấp phiếu). Nhờ vậy số ở
trang pivot luôn khớp với phiếu báo cáo SX và bảng lương tháng; sửa luật tính tiền ở
1 chỗ là cả 3 nơi cùng đổi.

Chỉ lấy thợ lương SẢN PHẨM (`production_workers.wage_type = 'product'`) — thợ lương
thời gian không có tiền theo phiếu nên đứng trong bảng này chỉ tổ cột rỗng.

Hình dạng trả về (tiền = ĐỒNG, số nguyên):
    {from, to,
     workers: [{id, name, total}],                       # thứ tự cột, đã bỏ thợ 0đ
     days: [{ymd, total, cells: {worker_id: money},
             slips: [{thread_id, code, start, end, total, cells: {...},
                      parts: {worker_id: [{code, cay, wage, gio, rate, money}]},
                      notes/pc/cay: {worker_id: ghi chú | phụ cấp | số cây}}]}],
     totals: {worker_id: money}, grand, max_cell, max_day}
`max_cell`/`max_day` để client tô đậm nhạt (heatmap) khỏi phải quét lại.
Nối: production_store.report_slips, worker_store. Client: webapp/src/pages/WagePivot.tsx.
"""
from __future__ import annotations

from datetime import date, timedelta


def _all_days(dfrom: str, dto: str) -> list[str]:
    """Mọi ngày YYYY-MM-DD trong [dfrom, dto]. Mốc hỏng / khoảng > 400 ngày → rỗng
    (chỉ giữ các ngày CÓ dữ liệu, không dựng bảng khổng lồ)."""
    try:
        start = date(*(int(x) for x in dfrom.split("-")))
        end = date(*(int(x) for x in dto.split("-")))
    except (AttributeError, ValueError, TypeError):
        return []
    if end < start or (end - start).days > 400:
        return []
    out, cur = [], start
    while cur <= end:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def wage_pivot(conn, dfrom: str, dto: str) -> dict:
    """Bảng pivot lương SP trong [dfrom, dto] (ngày YYYY-MM-DD, bao gồm 2 đầu)."""
    from production_store.report_slips import compute_range_report
    from worker_store import list_workers

    workers = [w for w in list_workers(conn) if (w.get("wage_type") or "product") == "product"]
    if not workers:
        return {"from": dfrom, "to": dto, "workers": [], "days": [],
                "totals": {}, "grand": 0, "max_cell": 0, "max_day": 0}

    by_name = {(w["name"] or "").strip().casefold(): w for w in workers}
    rep = compute_range_report(conn, dfrom, dto, worker_ids=[w["id"] for w in workers])

    # GHI CHÚ + PHỤ CẤP theo (phiếu, thợ) — để popup chi tiết 1 ô nói đủ chuyện, khỏi
    # phải mở phiếu ra xem. Ghi chú lấy từ dòng báo cáo; nhiều dòng thì nối bằng " · ".
    notes: dict[tuple, str] = {}
    cays: dict[tuple, float] = {}
    for r in conn.execute(
        "SELECT thread_id, worker_id, note, tong_calc FROM production_report_rows "
        "WHERE report_ymd >= ? AND report_ymd <= ?", (dfrom, dto),
    ).fetchall():
        key = (r["thread_id"], r["worker_id"])
        n = (r["note"] or "").strip()
        if n and n not in notes.get(key, ""):
            notes[key] = f"{notes[key]} · {n}" if notes.get(key) else n
        cays[key] = cays.get(key, 0.0) + float(r["tong_calc"] or 0)
    pcs: dict[tuple, float] = {}
    wid_by_name = {(w["name"] or "").strip(): w["id"] for w in workers}
    for r in conn.execute("SELECT thread_id, worker_name, amount FROM production_allowances").fetchall():
        wid2 = wid_by_name.get((r["worker_name"] or "").strip())
        if wid2 is not None:
            pcs[(r["thread_id"], wid2)] = float(r["amount"] or 0)

    # ── gom theo NGÀY rồi theo PHIẾU ────────────────────────────────────────────
    # days[ymd]["cells"][wid] = tiền của thợ đó trong ngày
    # days[ymd]["slips"][tid] = 1 phiếu SX (mã SP + giờ) kèm cells riêng
    days: dict[str, dict] = {}
    totals: dict[int, int] = {}
    for wk in rep.get("workers", []):
        w = by_name.get((wk.get("name") or "").strip().casefold())
        if not w:
            continue                      # thợ đã đổi tên/xoá — bỏ, không dựng cột lạ
        wid = w["id"]
        # compute_range_report trả days/items dạng LIST (đã sort), không phải dict
        for dy in (wk.get("days") or []):
            ymd = dy.get("ymd") or ""
            if not ymd:
                continue                  # dòng báo cáo không ghi ngày → không xếp vào lịch được
            money = int(dy.get("money") or 0)
            d = days.setdefault(ymd, {"ymd": ymd, "total": 0, "cells": {}, "slips": {}})
            d["cells"][wid] = d["cells"].get(wid, 0) + money
            d["total"] += money
            totals[wid] = totals.get(wid, 0) + money
            # cùng 1 phiếu có thể tách nhiều item (mã/đơn giá/dòng-giờ) → cộng dồn về phiếu
            for it in (dy.get("items") or []):
                tid = it.get("thread_id")
                if not tid:
                    continue
                s = d["slips"].setdefault(tid, {
                    "thread_id": tid, "code": it.get("code") or "",
                    "start": it.get("start") or "", "end": it.get("end") or "",
                    "total": 0, "cells": {}, "parts": {}, "notes": {}, "pc": {}, "cay": {},
                })
                m = int(it.get("money") or 0)
                s["cells"][wid] = s["cells"].get(wid, 0) + m
                s["total"] += m
                # CẤU THÀNH của ô: dòng cây (cay × wage) hoặc dòng giờ (gio × rate).
                # ⚠ phụ cấp phiếu đã được compute_range_report GỘP vào `money` của dòng
                # đầu, nên client phải tự lấy money − cay×wage làm phần "phụ cấp/khác"
                # chứ đừng tưởng cộng thiếu.
                s["parts"].setdefault(wid, []).append({
                    "code": it.get("code") or "", "cay": float(it.get("cay") or 0),
                    "wage": float(it.get("wage") or 0), "gio": float(it.get("gio") or 0),
                    "rate": float(it.get("hourly_rate") or 0), "money": m,
                })
                if not s["code"] and it.get("code"):
                    s["code"] = it["code"]
                nt = notes.get((tid, wid))
                if nt:
                    s["notes"][wid] = nt
                if pcs.get((tid, wid)):
                    s["pc"][wid] = pcs[(tid, wid)]
                if cays.get((tid, wid)):
                    s["cay"][wid] = round(cays[(tid, wid)], 1)

    # ── sắp xếp + dọn ───────────────────────────────────────────────────────────
    # ĐỦ MỌI NGÀY trong kỳ (ngày không ai làm vẫn có hàng, tiền 0) — bảng lương phải
    # nhìn ra được ngày nghỉ, chứ nhảy cóc 24→27 thì tưởng thiếu dữ liệu.
    for ymd in _all_days(dfrom, dto):
        days.setdefault(ymd, {"ymd": ymd, "total": 0, "cells": {}, "slips": {}})

    day_list = []
    max_cell = 0
    for ymd in sorted(days):
        d = days[ymd]
        slips = sorted(d["slips"].values(), key=lambda s: (s.get("start") or "", s["thread_id"]))
        for s in slips:
            s["cells"] = {str(k): v for k, v in s["cells"].items() if v}
            s["parts"] = {str(k): v for k, v in s.get("parts", {}).items() if s["cells"].get(str(k))}
            for fld in ("notes", "pc", "cay"):
                s[fld] = {str(k): v for k, v in s.get(fld, {}).items()}
        # thang màu heatmap lấy theo ô THEO NGÀY (ô phiếu luôn ≤ ô ngày nên cùng thang
        # thì view chi tiết nhạt đều — client tự chia thang riêng cho view phiếu)
        if d["cells"]:
            max_cell = max(max_cell, max(d["cells"].values()))
        day_list.append({"ymd": ymd, "total": d["total"],
                         "cells": {str(k): v for k, v in d["cells"].items() if v},
                         "slips": slips})

    # cột = thợ CÓ tiền trong kỳ, nhiều tiền đứng trước (nhìn bảng là thấy ai làm chính)
    cols = [{"id": w["id"], "name": w["name"], "total": totals.get(w["id"], 0)}
            for w in workers if totals.get(w["id"])]
    cols.sort(key=lambda c: (-c["total"], c["name"]))
    return {
        "from": dfrom, "to": dto,
        "workers": cols,
        "days": day_list,
        "totals": {str(k): v for k, v in totals.items() if v},
        "grand": sum(totals.values()),
        "max_cell": max_cell,
        "max_day": max([d["total"] for d in day_list] or [0]),
    }
