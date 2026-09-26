"""TĂNG CA của 1 phiếu SX đọc từ DB (mirror production_report_rows + giờ trong blob bang).

Giờ kết thúc CUỐI NGÀY của thợ quyết định có tăng ca hay không → phải đọc MỌI phiếu cùng
ngày báo cáo. Dùng bởi server_app.production_wages (khối tiền phiếu + #/tien-cong) và
production_store.allowance_auto (mốc phụ cấp = tiền SP ĐÃ GỒM tăng ca).
Nối: production_store.overtime (luật thuần), overtime_off (cờ tắt), time_fmt.
"""
from __future__ import annotations

import json

from production_store.overtime import overtime_map
from production_store.overtime_off import is_off, off_keys
from production_store.time_fmt import normalize_time


def overtime_for_rows(rows) -> dict:
    """Tăng ca theo giờ phiếu cho các dòng (cần cột tid/ymd/worker/cay/bang)
    → {(tid, thợ hiện hành): (phút TC, tỉ lệ)}."""
    times: dict = {}
    for r in rows:
        if r["tid"] not in times:
            try:
                b = json.loads(r["bang"] or "{}")
            except (TypeError, ValueError):
                b = {}
            times[r["tid"]] = (normalize_time(b.get("start")), normalize_time(b.get("end")))
    return overtime_map([(r["tid"], r["ymd"], r["worker"] or "?") for r in rows
                         if float(r["cay"] or 0) > 0], times)


def slip_overtime(conn, thread_id: int) -> dict:
    """{tên thợ trong báo cáo: {min, frac, off}} tăng ca của 1 phiếu (chỉ thợ có TC)."""
    rows = conn.execute(
        "SELECT t.thread_id AS tid, t.report_ymd AS ymd, t.worker_name AS wname, "
        "COALESCE(w.name, t.worker_name) AS worker, SUM(t.tong_calc) AS cay, s.bang AS bang "
        "FROM production_report_rows t "
        "LEFT JOIN production_workers w ON w.id = t.worker_id "
        "LEFT JOIN production_slips s ON s.thread_id = t.thread_id "
        "WHERE t.report_ymd IN (SELECT DISTINCT report_ymd FROM production_report_rows "
        "                       WHERE thread_id = ? AND report_ymd IS NOT NULL) "
        "GROUP BY t.thread_id, t.worker_name, COALESCE(w.name, t.worker_name)",
        (thread_id,),
    ).fetchall()
    ots = overtime_for_rows(rows)
    ot_off = off_keys(conn, [thread_id])
    out = {}
    for r in rows:
        v = ots.get((r["tid"], r["worker"] or "?"))
        if r["tid"] == thread_id and v:
            # off = văn phòng đã tắt TC dòng này → client hiện nút tắt, không cộng tiền
            out[r["wname"]] = {"min": v[0], "frac": round(v[1], 4),
                               "off": is_off(ot_off, thread_id, r["wname"])}
    return out


def same_day_slips(conn, thread_id: int) -> list[int]:
    """Các phiếu KHÁC có dòng báo cáo cùng ngày với phiếu này (TC của chúng có thể đổi
    khi phiếu này đổi giờ kết thúc)."""
    return [int(r[0]) for r in conn.execute(
        "SELECT DISTINCT thread_id FROM production_report_rows "
        "WHERE thread_id != ? AND report_ymd IN (SELECT DISTINCT report_ymd FROM "
        "  production_report_rows WHERE thread_id = ? AND report_ymd IS NOT NULL)",
        (thread_id, thread_id)).fetchall()]
