"""BÁO CÁO VỆ SINH khu vực — bảng `area_hygiene_reports` (app.db). 1 báo cáo còn
sống / (khu vực, ngày); get_or_create idempotent theo ngày. Ảnh gắn qua media scope
'area_report'. Dùng bởi server_app.area_routes; DDL ở area_store.schema.
"""
from __future__ import annotations

from datetime import datetime, timezone

from utils.db import transaction


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_report(conn, report_id) -> dict | None:
    row = conn.execute(
        "SELECT * FROM area_hygiene_reports WHERE id = ? AND deleted_at IS NULL", (report_id,)
    ).fetchone()
    return dict(row) if row else None


def get_or_create_report(conn, area_id, ymd: str, by: str | None = None, note: str = "") -> tuple[dict, bool]:
    """Trả (báo cáo, created). Idempotent theo (khu vực, ngày): đã có báo cáo CÒN
    SỐNG thì trả lại (created=False), chưa có thì tạo (created=True)."""
    with transaction(conn):
        row = conn.execute(
            "SELECT * FROM area_hygiene_reports WHERE area_id = ? AND ymd = ? AND deleted_at IS NULL",
            (area_id, ymd),
        ).fetchone()
        if row:
            return dict(row), False
        cur = conn.execute(
            "INSERT INTO area_hygiene_reports (area_id, ymd, note, created_at, created_by) "
            "VALUES (?, ?, ?, ?, ?)",
            (area_id, ymd, str(note or "").strip(), _now(), by or ""),
        )
        rid = cur.lastrowid
        new = conn.execute("SELECT * FROM area_hygiene_reports WHERE id = ?", (rid,)).fetchone()
    return dict(new), True


def list_reports(conn, area_id, limit: int = 60) -> list[dict]:
    """Báo cáo của 1 khu vực, mới nhất trước (bỏ xoá mềm)."""
    rows = conn.execute(
        "SELECT * FROM area_hygiene_reports WHERE area_id = ? AND deleted_at IS NULL "
        "ORDER BY ymd DESC, id DESC LIMIT ?",
        (area_id, int(limit)),
    ).fetchall()
    return [dict(r) for r in rows]


def list_reports_since(conn, ymd_from: str) -> list[dict]:
    """Mọi báo cáo còn sống của MỌI khu vực từ ymd_from trở đi (dashboard week strip)."""
    rows = conn.execute(
        "SELECT * FROM area_hygiene_reports WHERE ymd >= ? AND deleted_at IS NULL "
        "ORDER BY ymd DESC, id DESC",
        (ymd_from,),
    ).fetchall()
    return [dict(r) for r in rows]


def soft_delete_report(conn, report_id, by: str | None = None) -> tuple[bool, str | None]:
    with transaction(conn):
        row = conn.execute(
            "SELECT id, deleted_at FROM area_hygiene_reports WHERE id = ?", (report_id,)
        ).fetchone()
        if not row:
            return False, "Không tìm thấy báo cáo"
        if row["deleted_at"]:
            return False, "Báo cáo đã xoá rồi"
        conn.execute(
            "UPDATE area_hygiene_reports SET deleted_at = ?, deleted_by = ? WHERE id = ?",
            (_now(), by or "", report_id),
        )
    return True, None
