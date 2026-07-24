"""CRUD KHU VỰC XƯỞNG — bảng `workshop_areas` (app.db). Xoá mềm. created_at =
UTC ISO (như các store khác). Dùng bởi server_app.area_routes; DDL ở area_store.schema.
"""
from __future__ import annotations

from datetime import datetime, timezone

from utils.db import transaction


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(row) -> dict | None:
    return dict(row) if row else None


def list_areas(conn) -> list[dict]:
    """Khu vực chưa xoá — theo tên (khoá ổn định cho dashboard)."""
    rows = conn.execute(
        "SELECT * FROM workshop_areas WHERE deleted_at IS NULL ORDER BY name COLLATE NOCASE, id"
    ).fetchall()
    return [dict(r) for r in rows]


def get_area(conn, area_id) -> dict | None:
    row = conn.execute(
        "SELECT * FROM workshop_areas WHERE id = ? AND deleted_at IS NULL", (area_id,)
    ).fetchone()
    return _row(row)


def add_area(conn, name: str, note: str = "", by: str | None = None) -> tuple[dict | None, str | None]:
    name = str(name or "").strip()
    if not name:
        return None, "Cần nhập tên khu vực"
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO workshop_areas (name, note, created_at, created_by) VALUES (?, ?, ?, ?)",
            (name, str(note or "").strip(), _now(), by or ""),
        )
        area_id = cur.lastrowid
    return get_area(conn, area_id), None


def update_area(conn, area_id, *, name: str | None = None, note: str | None = None) -> tuple[dict | None, str | None]:
    area = get_area(conn, area_id)
    if not area:
        return None, "Không tìm thấy khu vực"
    sets, args = [], []
    if name is not None:
        n = str(name).strip()
        if not n:
            return None, "Tên khu vực không được rỗng"
        sets.append("name = ?")
        args.append(n)
    if note is not None:
        sets.append("note = ?")
        args.append(str(note).strip())
    if not sets:
        return area, None
    args.append(area_id)
    with transaction(conn):
        conn.execute(f"UPDATE workshop_areas SET {', '.join(sets)} WHERE id = ?", args)
    return get_area(conn, area_id), None


def soft_delete_area(conn, area_id, by: str | None = None) -> tuple[bool, str | None]:
    with transaction(conn):
        row = conn.execute(
            "SELECT id, deleted_at FROM workshop_areas WHERE id = ?", (area_id,)
        ).fetchone()
        if not row:
            return False, "Không tìm thấy khu vực"
        if row["deleted_at"]:
            return False, "Khu vực đã xoá rồi"
        conn.execute(
            "UPDATE workshop_areas SET deleted_at = ?, deleted_by = ? WHERE id = ?",
            (_now(), by or "", area_id),
        )
    return True, None
