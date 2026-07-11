"""CRUD danh sách thợ (production_workers) — IO + transaction, không logic thuần.

1 row = 1 thợ. name UNIQUE (không phân biệt hoa/thường). is_default = thợ có trong
mẫu báo cáo mặc định. sort_order để sắp thứ tự chèn. Nối: utils.db.
"""
from __future__ import annotations

from utils.db import transaction


def ensure_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS production_workers (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL COLLATE NOCASE,
            is_default INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_worker_name ON production_workers(name)")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(production_workers)").fetchall()}
    if "weekly_salary" not in cols:
        conn.execute("ALTER TABLE production_workers ADD COLUMN weekly_salary INTEGER DEFAULT 0")
    conn.commit()


def _row(r) -> dict:
    return {
        "id": r["id"], "name": r["name"], "is_default": bool(r["is_default"]),
        "sort_order": r["sort_order"], "weekly_salary": bool(r["weekly_salary"]),
    }


def list_workers(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT id, name, is_default, sort_order, weekly_salary FROM production_workers "
        "ORDER BY sort_order ASC, name COLLATE NOCASE ASC"
    ).fetchall()
    return [_row(r) for r in rows]


def default_names(conn) -> list[str]:
    """Tên các thợ mặc định (đúng thứ tự) — dùng làm template báo cáo."""
    rows = conn.execute(
        "SELECT name FROM production_workers WHERE is_default = 1 "
        "ORDER BY sort_order ASC, name COLLATE NOCASE ASC"
    ).fetchall()
    return [r["name"] for r in rows]


def add_worker(conn, name: str, is_default: bool = False) -> dict:
    nm = (name or "").strip()
    if not nm:
        raise ValueError("Tên thợ trống")
    with transaction(conn):
        dup = conn.execute("SELECT id FROM production_workers WHERE name = ? COLLATE NOCASE", (nm,)).fetchone()
        if dup:
            raise ValueError("Thợ đã có trong danh sách")
        mx = conn.execute("SELECT COALESCE(MAX(sort_order), 0) AS m FROM production_workers").fetchone()["m"]
        cur = conn.execute(
            "INSERT INTO production_workers (name, is_default, sort_order) VALUES (?, ?, ?)",
            (nm, 1 if is_default else 0, int(mx) + 1),
        )
        wid = cur.lastrowid
    return {"id": wid, "name": nm, "is_default": bool(is_default), "sort_order": int(mx) + 1, "weekly_salary": False}


def update_worker(
    conn, worker_id: int, *,
    name: str | None = None, is_default: bool | None = None, weekly_salary: bool | None = None,
) -> dict | None:
    """Sửa thợ. ĐỔI TÊN = cascade cùng transaction: production_report_rows (dòng
    đã gán worker_id đổi nhãn; dòng cổ trùng tên cũ được GÁN id + nhãn mới) + blob
    `bang` các phiếu SX (tên thợ trong báo cáo đã lưu) — lịch sử dashboard/chi tiết
    thợ KHÔNG tách đôi khi sửa tên."""
    with transaction(conn):
        cur = conn.execute(
            "SELECT id, name, is_default, sort_order, weekly_salary FROM production_workers WHERE id = ?",
            (worker_id,),
        ).fetchone()
        if not cur:
            return None
        new_name = cur["name"] if name is None else (name or "").strip()
        if not new_name:
            raise ValueError("Tên thợ trống")
        renaming = name is not None and new_name != cur["name"]
        if renaming and new_name.lower() != cur["name"].lower():
            dup = conn.execute(
                "SELECT id FROM production_workers WHERE name = ? COLLATE NOCASE AND id <> ?", (new_name, worker_id)
            ).fetchone()
            if dup:
                raise ValueError("Thợ đã có trong danh sách")
        new_def = cur["is_default"] if is_default is None else (1 if is_default else 0)
        new_wk = cur["weekly_salary"] if weekly_salary is None else (1 if weekly_salary else 0)
        conn.execute(
            "UPDATE production_workers SET name = ?, is_default = ?, weekly_salary = ? WHERE id = ?",
            (new_name, new_def, new_wk, worker_id),
        )
        if renaming:
            _cascade_rename(conn, worker_id, cur["name"], new_name)
    return {
        "id": worker_id, "name": new_name, "is_default": bool(new_def),
        "sort_order": cur["sort_order"], "weekly_salary": bool(new_wk),
    }


def _cascade_rename(conn, worker_id: int, old_name: str, new_name: str) -> None:
    """Đổi nhãn tên thợ ở mọi nơi đang lưu snapshot (bảng mirror + blob bang)."""
    import json
    try:
        conn.execute(
            "UPDATE production_report_rows SET worker_name = ? WHERE worker_id = ?",
            (new_name, worker_id),
        )
        # dòng cổ chưa gán id nhưng trùng tên cũ → nhận danh tính luôn
        conn.execute(
            "UPDATE production_report_rows SET worker_id = ?, worker_name = ? "
            "WHERE worker_id IS NULL AND TRIM(worker_name) = TRIM(?) COLLATE NOCASE",
            (worker_id, new_name, old_name),
        )
    except Exception:  # noqa: BLE001 — bảng chưa tạo (DB test)
        pass
    try:
        old_cf = old_name.strip().casefold()
        rows = conn.execute(
            "SELECT thread_id, bang FROM production_slips WHERE bang IS NOT NULL AND bang != ''"
        ).fetchall()
        for tid, btext in rows:
            try:
                bang = json.loads(btext)
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(bang, dict):
                continue
            dirty = False
            for r in bang.get("rows") or []:
                if isinstance(r, dict) and str(r.get("name") or "").strip().casefold() == old_cf:
                    r["name"] = new_name
                    dirty = True
            if dirty:
                conn.execute(
                    "UPDATE production_slips SET bang = ? WHERE thread_id = ?",
                    (json.dumps(bang, ensure_ascii=False), tid),
                )
    except Exception:  # noqa: BLE001 — bảng chưa tạo (DB test)
        pass


def reorder_workers(conn, ids: list[int]) -> None:
    """Đặt lại sort_order theo đúng thứ tự `ids` truyền vào (0, 1, 2, …).
    id không tồn tại được bỏ qua (UPDATE không khớp = no-op)."""
    with transaction(conn):
        for i, wid in enumerate(ids):
            conn.execute(
                "UPDATE production_workers SET sort_order = ? WHERE id = ?",
                (i, int(wid)),
            )


def delete_worker(conn, worker_id: int) -> bool:
    with transaction(conn):
        cur = conn.execute("DELETE FROM production_workers WHERE id = ?", (worker_id,))
        return cur.rowcount > 0
