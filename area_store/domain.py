"""Logic THUẦN cho khu vực xưởng + báo cáo vệ sinh (KHÔNG IO, unit-tested).

today_vn / last_n_days = mốc ngày; build_dashboard_rows = ghép khu vực + báo cáo
(kèm số ảnh) → hàng dashboard (đã báo cáo hôm nay + dải 7 ngày). Dùng bởi
area_store.reports/queries và server_app.area_routes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

_VN_TZ = timezone(timedelta(hours=7))


def today_vn() -> str:
    """Ngày hôm nay theo giờ VN (UTC+7), dạng 'YYYY-MM-DD'."""
    return datetime.now(_VN_TZ).strftime("%Y-%m-%d")


def last_n_days(today_ymd: str, n: int) -> list[str]:
    """n ngày gần nhất KẾT THÚC ở today_ymd (cũ → mới), gồm cả hôm nay.
    last_n_days('2026-07-24', 7) → [...'2026-07-18'..'2026-07-24']."""
    if n <= 0:
        return []
    base = datetime.strptime(today_ymd, "%Y-%m-%d")
    return [(base - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n - 1, -1, -1)]


def build_dashboard_rows(
    areas: list[dict],
    reports: list[dict],
    today_ymd: str,
    *,
    week: int = 7,
) -> tuple[list[dict], int]:
    """Ghép danh sách khu vực + báo cáo (mỗi báo cáo có 'photo_count') → hàng dashboard.

    areas = [{id, name, note, ...}] (đã bỏ xoá mềm).
    reports = [{id, area_id, ymd, created_at, created_by, photo_count}] (đã bỏ xoá mềm).
    Mỗi khu vực: today {report_id, photo_count, reported}, last_report, week[7].
    'reported' CHỈ đúng khi báo cáo có ≥1 ảnh (photo_count >= 1).
    """
    days = last_n_days(today_ymd, week)
    # gom báo cáo theo (area_id, ymd) — 1 báo cáo sống / khu / ngày, nhưng phòng thủ
    by_area_day: dict[tuple[int, str], dict] = {}
    latest_by_area: dict[int, dict] = {}
    for r in reports:
        aid = int(r.get("area_id"))
        ymd = str(r.get("ymd") or "")
        by_area_day[(aid, ymd)] = r
        prev = latest_by_area.get(aid)
        if prev is None or (str(r.get("created_at") or "")) > str(prev.get("created_at") or ""):
            latest_by_area[aid] = r

    def _reported(rep: dict | None) -> bool:
        return bool(rep) and int(rep.get("photo_count") or 0) >= 1

    rows: list[dict] = []
    done = 0
    for a in areas:
        aid = int(a["id"])
        today_rep = by_area_day.get((aid, today_ymd))
        today_ok = _reported(today_rep)
        if today_ok:
            done += 1
        last = latest_by_area.get(aid)
        rows.append({
            "id": aid,
            "name": a.get("name") or "",
            "note": a.get("note") or "",
            "today": {
                "report_id": int(today_rep["id"]) if today_rep else None,
                "photo_count": int(today_rep.get("photo_count") or 0) if today_rep else 0,
                "reported": today_ok,
            },
            "last_report": None if not last else {
                "ymd": last.get("ymd"),
                "created_at": last.get("created_at"),
                "created_by": last.get("created_by") or "",
            },
            "week": [{"ymd": d, "reported": _reported(by_area_day.get((aid, d)))} for d in days],
        })
    return rows, done
