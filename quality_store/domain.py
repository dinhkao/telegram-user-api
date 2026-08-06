"""Logic THUẦN cho báo cáo chất lượng mâm kẹo (KHÔNG IO, unit-tested).

Mốc ngày + ghép hàng dashboard dùng chung với báo cáo vệ sinh khu vực →
utils/daily_photo_report.py; file này chỉ chốt entity_key='worker_id' (thực thể =
THỢ trong bảng production_workers). Dùng bởi server_app.quality_routes.
"""
from __future__ import annotations

from utils.daily_photo_report import last_n_days, today_vn

__all__ = ["today_vn", "last_n_days", "build_dashboard_rows", "clean_board_ids", "select_board_rows"]


def clean_board_ids(raw, valid_ids=None) -> list[int]:
    """Chuẩn hoá cấu hình 'thợ nào hiện trên bảng' (settings_store lưu JSON tự do).
    Bỏ giá trị không phải số, bỏ TRÙNG, GIỮ NGUYÊN thứ tự người dùng đã sắp (thứ tự
    = vị trí ô trong lưới 2 cột). valid_ids != None thì bỏ luôn thợ đã xoá."""
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    for v in raw:
        if isinstance(v, bool):        # True/False lọt vào int() thành 1/0 → chặn
            continue
        try:
            i = int(v)
        except (TypeError, ValueError):
            continue
        if valid_ids is not None and i not in valid_ids:
            continue
        if i not in out:
            out.append(i)
    return out


def select_board_rows(rows: list[dict], board_ids: list[int]) -> list[dict]:
    """Lọc + SẮP hàng dashboard theo cấu hình bảng. board_ids rỗng = giữ tất cả
    (chưa cấu hình → hành vi cũ). Id không còn thợ thì bỏ qua, không lỗi."""
    if not board_ids:
        return list(rows)
    by = {int(r["id"]): r for r in rows}
    return [by[i] for i in board_ids if i in by]


def build_dashboard_rows(
    workers: list[dict],
    reports: list[dict],
    today_ymd: str,
    *,
    week: int = 7,
) -> tuple[list[dict], int]:
    """Ghép thợ + báo cáo chất lượng (mỗi báo cáo có 'photo_count') → hàng dashboard.
    Xem utils.daily_photo_report.build_dashboard_rows; báo cáo trỏ thợ qua 'worker_id'."""
    from utils.daily_photo_report import build_dashboard_rows as _build
    return _build(workers, reports, today_ymd, entity_key="worker_id", week=week)
