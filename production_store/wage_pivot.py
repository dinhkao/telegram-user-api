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
             slips: [{thread_id, code, kind, start, end, total, cells: {...},
                      parts: {worker_id: [{code, cay, wage, gio, rate, money, ot, ot_min}]},
                      notes/pc/pc_by/cay/ot_off: {worker_id: ghi chú | phụ cấp |
                      người ghi phụ cấp ("auto" = rule) | số cây | True = đã tắt TC},
                      flag: {worker_id: {kind, done}} = ghi chú LỆCH CHUẨN → auto không
                      trả phụ cấp, ô gắn ⚠ (done = đã tick xử lý / đã nhập tay)}]}],
     totals: {worker_id: money}, grand, max_cell, max_day}
`max_cell`/`max_day` để client tô đậm nhạt (heatmap) khỏi phải quét lại.
Nối: production_store.report_slips, note_review + note_resolved (dấu ⚠), worker_store. Client: webapp/src/pages/WagePivot.tsx.
"""
from __future__ import annotations

from datetime import date, timedelta

from production_store.time_fmt import time_minutes


# Mốc (UTC, như production_note_resolved.resolved_at) đổi luật phụ cấp tự động sang TRÙNG
# KHÍT câu chuẩn — tick "đã xử lý" trước mốc này không còn giá trị cho dấu ⚠.
EXACT_RULE_SINCE = "2026-09-26 08:00:00"


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


def _time_key(start: str | None) -> tuple[int, int]:
    """Khoá SẮP XẾP phiếu theo GIỜ BẮT ĐẦU. Phải quy về PHÚT chứ không so chuỗi:
    "7:00" (1 chữ số giờ) so chuỗi sẽ đứng SAU "13:00" — đúng lỗi phiếu xếp lộn xộn.
    Phiếu không có giờ xếp CUỐI (không đoán chỗ cho nó)."""
    mins = time_minutes(start)
    return (1, 0) if mins is None else (0, mins)


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
    # GHI CHÚ LỆCH CHUẨN (production_store.note_review) → dấu ⚠ ở ô: auto phụ cấp chỉ
    # trả khi ghi chú trùng khít câu chuẩn, lệch là văn phòng phải tự quyết.
    # flags[(phiếu, thợ)] = (loại, đã tick xử lý ở khối cảnh báo #/sx-bang hay chưa)
    from production_store.note_resolved import ensure_schema as _ensure_resolved
    from production_store.note_review import fold_note, needs_review
    # Chỉ tick "đã xử lý" SAU khi đổi luật mới tính: tick trước đó nghĩa là "auto trả thế
    # là đúng", mà nay auto không trả nữa (đã đặt về 0) → ô phải hiện lại cho người xem.
    _ensure_resolved(conn)
    resolved = {(int(r[0]), str(r[1] or ""), str(r[2] or "")) for r in conn.execute(
        "SELECT thread_id, worker_name, note_fold FROM production_note_resolved WHERE resolved_at >= ?",
        (EXACT_RULE_SINCE,)).fetchall()}
    wname_by_id = {w["id"]: w["name"] for w in workers}
    raws: dict[tuple, str] = {}     # tên thợ THÔ trong báo cáo = khoá production_allowances
    flags: dict[tuple, tuple[str, bool, str]] = {}   # (loại, đã xử lý, ghi chú thô của dòng)
    for r in conn.execute(
        "SELECT thread_id, worker_id, worker_name, note, tong_calc FROM production_report_rows "
        "WHERE report_ymd >= ? AND report_ymd <= ?", (dfrom, dto),
    ).fetchall():
        key = (r["thread_id"], r["worker_id"])
        n = (r["note"] or "").strip()
        if n and n not in notes.get(key, ""):
            notes[key] = f"{notes[key]} · {n}" if notes.get(key) else n
        cays[key] = cays.get(key, 0.0) + float(r["tong_calc"] or 0)
        raws.setdefault(key, str(r["worker_name"] or "").strip())
        kind = needs_review(wname_by_id.get(r["worker_id"]) or r["worker_name"] or "", n) if n else ""
        if kind:
            done = (int(r["thread_id"]), str(r["worker_name"] or ""), fold_note(n)) in resolved
            old = flags.get(key)
            flags[key] = (kind, done and (old is None or old[1]), n)
    pcs: dict[tuple, float] = {}
    pc_by: dict[tuple, str] = {}          # ai ghi phụ cấp: "auto" (rule ghi chú) | username
    wid_by_name = {(w["name"] or "").strip().casefold(): w["id"] for w in workers}
    for r in conn.execute("SELECT thread_id, worker_name, amount, updated_by FROM production_allowances").fetchall():
        wid2 = wid_by_name.get((r["worker_name"] or "").strip().casefold())
        if wid2 is not None:
            pcs[(r["thread_id"], wid2)] = float(r["amount"] or 0)
            pc_by[(r["thread_id"], wid2)] = r["updated_by"] or ""
    # dòng văn phòng đã TẮT tăng ca + loại phiếu — để popup nói rõ vì sao TC = 0
    from production_store.overtime_off import off_keys
    tids_all = {it.get("thread_id") for wk in rep.get("workers", []) for dy in (wk.get("days") or [])
                for it in (dy.get("items") or []) if it.get("thread_id")}
    ot_off = off_keys(conn, tids_all)
    kinds: dict[int, str] = {}
    if tids_all:
        qs = ",".join("?" * len(tids_all))
        kinds = {int(r[0]): (r[1] or "san_xuat") for r in conn.execute(
            f"SELECT thread_id, kind FROM production_slips WHERE thread_id IN ({qs})", sorted(tids_all))}

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
                    "kind": kinds.get(tid, "san_xuat"),
                    "total": 0, "cells": {}, "parts": {}, "notes": {}, "pc": {}, "pc_by": {},
                    "cay": {}, "ot_off": {}, "flag": {}, "raw": {},
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
                    # phụ trội TĂNG CA (đã nằm trong money) — popup tách riêng khỏi "phụ cấp"
                    "ot": int(it.get("ot_money") or 0), "ot_min": int(it.get("ot_min") or 0),
                })
                if not s["code"] and it.get("code"):
                    s["code"] = it["code"]
                nt = notes.get((tid, wid))
                if nt:
                    s["notes"][wid] = nt
                if pcs.get((tid, wid)):
                    s["pc"][wid] = pcs[(tid, wid)]
                    s["pc_by"][wid] = pc_by.get((tid, wid), "")
                if (int(tid), (wk.get("name") or "").strip().casefold()) in ot_off:
                    s["ot_off"][wid] = True

                if cays.get((tid, wid)):
                    s["cay"][wid] = round(cays[(tid, wid)], 1)

    # ── DẤU ⚠ + ghi chú cho MỌI (phiếu, thợ) có ghi chú lệch chuẩn — kể cả ô 0đ: thợ
    # không làm cây mà phụ cấp vừa bị đặt về 0 thì compute_range_report không có dòng nào,
    # nhưng đó lại chính là ô cần văn phòng chú ý nhất.
    slip_by_tid = {tid: sl for d in days.values() for tid, sl in d["slips"].items()}
    for (tid, wid), raw in raws.items():
        sl = slip_by_tid.get(tid)
        if sl is not None and wid in wname_by_id:
            sl["raw"][wid] = raw        # popup sửa phụ cấp gửi ĐÚNG tên này (khớp khoá phụ cấp)
    for (tid, wid), fl in flags.items():
        sl = slip_by_tid.get(tid)
        if sl is None or wid not in wname_by_id:   # thợ lương thời gian: không có cột ở trang này
            continue
        # done = đã tick xử lý (sau khi đổi luật) HOẶC văn phòng đã nhập tay phụ cấp
        by = pc_by.get((tid, wid), "")
        # note = ghi chú THÔ đúng dòng bị gắn dấu — khoá tick "đã xử lý" (note_resolved) cần nó
        sl["flag"][wid] = {"kind": fl[0], "done": fl[1] or (bool(pcs.get((tid, wid))) and by not in ("", "auto")),
                           "note": fl[2]}
        if notes.get((tid, wid)):
            sl["notes"][wid] = notes[(tid, wid)]
        if cays.get((tid, wid)):
            sl["cay"][wid] = round(cays[(tid, wid)], 1)

    # ── sắp xếp + dọn ───────────────────────────────────────────────────────────
    # ĐỦ MỌI NGÀY trong kỳ (ngày không ai làm vẫn có hàng, tiền 0) — bảng lương phải
    # nhìn ra được ngày nghỉ, chứ nhảy cóc 24→27 thì tưởng thiếu dữ liệu.
    for ymd in _all_days(dfrom, dto):
        days.setdefault(ymd, {"ymd": ymd, "total": 0, "cells": {}, "slips": {}})

    day_list = []
    max_cell = 0
    for ymd in sorted(days):
        d = days[ymd]
        slips = sorted(d["slips"].values(), key=lambda s: (_time_key(s.get("start")), s["thread_id"]))
        for s in slips:
            s["cells"] = {str(k): v for k, v in s["cells"].items() if v}
            s["parts"] = {str(k): v for k, v in s.get("parts", {}).items() if s["cells"].get(str(k))}
            for fld in ("notes", "pc", "pc_by", "cay", "ot_off", "flag", "raw"):
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
