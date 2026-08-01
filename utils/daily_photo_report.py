"""Logic THUẦN dùng chung cho các dashboard BÁO CÁO-ẢNH-HẰNG-NGÀY (KHÔNG IO,
unit-tested): vệ sinh khu vực (area_store) + chất lượng mâm kẹo (quality_store).

Cùng một hình dạng: 1 danh sách thực thể (khu vực / thợ) × 1 báo cáo còn sống mỗi
(thực thể, ngày), báo cáo chỉ tính là XONG khi có ≥1 ảnh. today_vn/last_n_days =
mốc ngày VN; build_dashboard_rows = ghép thực thể + báo cáo → hàng dashboard.
Dùng bởi area_store.domain, quality_store.domain.
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
    entities: list[dict],
    reports: list[dict],
    today_ymd: str,
    *,
    entity_key: str,
    week: int = 7,
) -> tuple[list[dict], int]:
    """Ghép danh sách thực thể + báo cáo (mỗi báo cáo có 'photo_count') → (hàng, số xong).

    entities = [{id, name, note, ...}] (đã bỏ xoá mềm).
    reports = [{id, <entity_key>, ymd, created_at, created_by, photo_count}] (đã bỏ xoá mềm);
    entity_key = tên cột trỏ về thực thể ('area_id' | 'worker_id').
    Mỗi hàng: today {report_id, photo_count, reported}, last_report, week[n].
    'reported' CHỈ đúng khi báo cáo có ≥1 ảnh (photo_count >= 1).
    """
    days = last_n_days(today_ymd, week)
    # gom báo cáo theo (entity, ymd) — 1 báo cáo sống / thực thể / ngày, nhưng phòng thủ
    by_ent_day: dict[tuple[int, str], dict] = {}
    latest_by_ent: dict[int, dict] = {}
    for r in reports:
        eid = int(r.get(entity_key))
        ymd = str(r.get("ymd") or "")
        by_ent_day[(eid, ymd)] = r
        prev = latest_by_ent.get(eid)
        if prev is None or (str(r.get("created_at") or "")) > str(prev.get("created_at") or ""):
            latest_by_ent[eid] = r

    def _reported(rep: dict | None) -> bool:
        return bool(rep) and int(rep.get("photo_count") or 0) >= 1

    rows: list[dict] = []
    done = 0
    for e in entities:
        eid = int(e["id"])
        today_rep = by_ent_day.get((eid, today_ymd))
        today_ok = _reported(today_rep)
        if today_ok:
            done += 1
        last = latest_by_ent.get(eid)
        rows.append({
            "id": eid,
            "name": e.get("name") or "",
            "note": e.get("note") or "",
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
            "week": [{"ymd": d, "reported": _reported(by_ent_day.get((eid, d)))} for d in days],
        })
    return rows, done
