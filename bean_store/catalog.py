"""DANH MỤC kho đậu — loại đậu (`beans`) + vị trí kho (`bean_places`) trong app.db.

Hai bảng cùng hình dạng (tên/ghi chú/xoá mềm) nên dùng chung một bộ CRUD; đậu có
thêm cột `unit` (kg/bao…). created_at = UTC ISO như các store khác. DDL ở
bean_store.schema; dùng bởi bean_store.slips/stock và server_app.bean_routes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from utils.db import transaction

_TABLES = {"bean": "beans", "place": "bean_places"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _list(conn, what: str) -> list[dict]:
    rows = conn.execute(
        f"SELECT * FROM {_TABLES[what]} WHERE deleted_at IS NULL "
        "ORDER BY name COLLATE NOCASE, id"
    ).fetchall()
    return [dict(r) for r in rows]


def _get(conn, what: str, row_id) -> dict | None:
    row = conn.execute(
        f"SELECT * FROM {_TABLES[what]} WHERE id = ? AND deleted_at IS NULL", (row_id,)
    ).fetchone()
    return dict(row) if row else None


def _name_taken(conn, what: str, name: str, exclude_id=None) -> bool:
    """Trùng tên? So bằng Python .lower() chứ KHÔNG dùng COLLATE NOCASE — SQLite chỉ
    fold được ASCII nên 'Đậu xanh' và 'đậu xanh' lọt qua thành 2 dòng."""
    target = str(name or "").strip().lower()
    rows = conn.execute(
        f"SELECT id, name FROM {_TABLES[what]} WHERE deleted_at IS NULL"
    ).fetchall()
    return any(str(r["name"] or "").strip().lower() == target
               and (exclude_id is None or int(r["id"]) != int(exclude_id))
               for r in rows)


# ── Loại đậu ─────────────────────────────────────────────────────────────────
def list_beans(conn) -> list[dict]:
    return _list(conn, "bean")


def get_bean(conn, bean_id) -> dict | None:
    return _get(conn, "bean", bean_id)


def add_bean(conn, name: str, unit: str = "kg", note: str = "",
             by: str | None = None) -> tuple[dict | None, str | None]:
    name = str(name or "").strip()
    if not name:
        return None, "Cần nhập tên loại đậu"
    unit = str(unit or "").strip() or "kg"
    with transaction(conn):
        if _name_taken(conn, "bean", name):
            return None, f'Đã có loại đậu tên "{name}"'
        cur = conn.execute(
            "INSERT INTO beans (name, unit, note, created_at, created_by) VALUES (?, ?, ?, ?, ?)",
            (name, unit, str(note or "").strip(), _now(), by or ""),
        )
        bean_id = cur.lastrowid
    return get_bean(conn, bean_id), None


def update_bean(conn, bean_id, *, name: str | None = None, unit: str | None = None,
                note: str | None = None) -> tuple[dict | None, str | None]:
    bean = get_bean(conn, bean_id)
    if not bean:
        return None, "Không tìm thấy loại đậu"
    sets, args = [], []
    if name is not None:
        n = str(name).strip()
        if not n:
            return None, "Tên loại đậu không được rỗng"
        if _name_taken(conn, "bean", n, exclude_id=bean_id):
            return None, f'Đã có loại đậu tên "{n}"'
        sets.append("name = ?")
        args.append(n)
    if unit is not None:
        sets.append("unit = ?")
        args.append(str(unit).strip() or "kg")
    if note is not None:
        sets.append("note = ?")
        args.append(str(note).strip())
    if not sets:
        return bean, None
    args.append(bean_id)
    with transaction(conn):
        conn.execute(f"UPDATE beans SET {', '.join(sets)} WHERE id = ?", args)
    return get_bean(conn, bean_id), None


def soft_delete_bean(conn, bean_id, by: str | None = None) -> tuple[bool, str | None]:
    """Xoá mềm loại đậu. CHẶN khi còn phiếu còn sống nhắc tới nó (tồn/lịch sử sẽ hụt)."""
    with transaction(conn):
        row = conn.execute("SELECT id, deleted_at FROM beans WHERE id = ?", (bean_id,)).fetchone()
        if not row:
            return False, "Không tìm thấy loại đậu"
        if row["deleted_at"]:
            return False, "Loại đậu đã xoá rồi"
        used = conn.execute(
            "SELECT COUNT(*) c FROM bean_moves m JOIN bean_slips s ON s.id = m.slip_id "
            "WHERE m.bean_id = ? AND s.deleted_at IS NULL", (bean_id,)
        ).fetchone()["c"]
        if used:
            return False, f"Loại đậu đang có {used} dòng phiếu — xoá phiếu trước"
        conn.execute("UPDATE beans SET deleted_at = ?, deleted_by = ? WHERE id = ?",
                     (_now(), by or "", bean_id))
    return True, None


# ── Vị trí kho ───────────────────────────────────────────────────────────────
def list_places(conn) -> list[dict]:
    return _list(conn, "place")


def get_place(conn, place_id) -> dict | None:
    return _get(conn, "place", place_id)


def add_place(conn, name: str, note: str = "",
              by: str | None = None) -> tuple[dict | None, str | None]:
    name = str(name or "").strip()
    if not name:
        return None, "Cần nhập tên kho"
    with transaction(conn):
        if _name_taken(conn, "place", name):
            return None, f'Đã có kho tên "{name}"'
        cur = conn.execute(
            "INSERT INTO bean_places (name, note, created_at, created_by) VALUES (?, ?, ?, ?)",
            (name, str(note or "").strip(), _now(), by or ""),
        )
        place_id = cur.lastrowid
    return get_place(conn, place_id), None


def update_place(conn, place_id, *, name: str | None = None,
                 note: str | None = None) -> tuple[dict | None, str | None]:
    place = get_place(conn, place_id)
    if not place:
        return None, "Không tìm thấy kho"
    sets, args = [], []
    if name is not None:
        n = str(name).strip()
        if not n:
            return None, "Tên kho không được rỗng"
        if _name_taken(conn, "place", n, exclude_id=place_id):
            return None, f'Đã có kho tên "{n}"'
        sets.append("name = ?")
        args.append(n)
    if note is not None:
        sets.append("note = ?")
        args.append(str(note).strip())
    if not sets:
        return place, None
    args.append(place_id)
    with transaction(conn):
        conn.execute(f"UPDATE bean_places SET {', '.join(sets)} WHERE id = ?", args)
    return get_place(conn, place_id), None


def soft_delete_place(conn, place_id, by: str | None = None) -> tuple[bool, str | None]:
    """Xoá mềm kho. CHẶN khi còn phiếu còn sống ở kho đó."""
    with transaction(conn):
        row = conn.execute("SELECT id, deleted_at FROM bean_places WHERE id = ?",
                           (place_id,)).fetchone()
        if not row:
            return False, "Không tìm thấy kho"
        if row["deleted_at"]:
            return False, "Kho đã xoá rồi"
        used = conn.execute(
            "SELECT COUNT(*) c FROM bean_slips WHERE place_id = ? AND deleted_at IS NULL",
            (place_id,)
        ).fetchone()["c"]
        if used:
            return False, f"Kho đang có {used} phiếu — xoá phiếu trước"
        conn.execute("UPDATE bean_places SET deleted_at = ?, deleted_by = ? WHERE id = ?",
                     (_now(), by or "", place_id))
    return True, None
