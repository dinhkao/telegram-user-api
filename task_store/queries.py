"""CRUD + truy vấn bảng `tasks` — list theo filter, đếm theo ngày (calendar).

Nối: task_store.schema (conn). Dùng bởi: server_app/task_routes, task_store.mirror.
"""
from __future__ import annotations

import time

from .schema import COLS, conn_tasks


def _row(r) -> dict:
    d = dict(r)
    d["done"] = bool(d.get("done"))
    return d


def create_task(*, title: str, note: str = "", assignee: str = "", due_at: str | None = None,
                thread_id: int | None = None, order_label: str = "", created_by: str = "",
                kind: str = "free", step_key: str | None = None) -> dict:
    now = int(time.time())
    conn = conn_tasks()
    try:
        cur = conn.execute(
            "INSERT INTO web_tasks (kind, thread_id, step_key, title, note, order_label, assignee, due_at,"
            " created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (kind, thread_id, step_key, title.strip(), note.strip(), order_label, assignee, due_at or None,
             created_by, now, now),
        )
        return get_task(int(cur.lastrowid))
    finally:
        conn.close()


def get_task(task_id: int) -> dict | None:
    conn = conn_tasks()
    try:
        r = conn.execute(f"SELECT {COLS} FROM web_tasks WHERE id = ?", (int(task_id),)).fetchone()
        return _row(r) if r else None
    finally:
        conn.close()


_FIELDS = {"title", "note", "assignee", "due_at", "order_label", "thread_id"}


def update_task(task_id: int, fields: dict) -> dict | None:
    """Sửa các trường cho phép (title/note/assignee/due_at/thread_id/order_label)."""
    sets, vals = [], []
    for k, v in fields.items():
        if k in _FIELDS:
            sets.append(f"{k} = ?")
            vals.append(v if v not in ("",) or k in ("note", "assignee", "order_label") else None)
    if not sets:
        return get_task(task_id)
    conn = conn_tasks()
    try:
        conn.execute(f"UPDATE web_tasks SET {', '.join(sets)}, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                     vals + [int(time.time()), int(task_id)])
        return get_task(task_id)
    finally:
        conn.close()


def set_done(task_id: int, done: bool, by: str = "") -> dict | None:
    now = int(time.time())
    conn = conn_tasks()
    try:
        conn.execute(
            "UPDATE web_tasks SET done = ?, done_by = ?, done_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
            (1 if done else 0, by if done else None, now if done else None, now, int(task_id)),
        )
        return get_task(task_id)
    finally:
        conn.close()


def soft_delete(task_id: int) -> bool:
    conn = conn_tasks()
    try:
        cur = conn.execute("UPDATE web_tasks SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
                           (int(time.time()), int(task_id)))
        return cur.rowcount > 0
    finally:
        conn.close()


def list_tasks(*, flt: str = "open", assignee: str = "", me: str = "", page: int = 1,
               per_page: int = 30, today: str = "") -> tuple[list[dict], int]:
    """Danh sách theo filter: open (chưa xong) | free (việc tự tạo) | order (từ đơn)
    | mine (phân công cho tôi, chưa xong) | overdue (quá hạn) | done | all."""
    where, params = ["deleted_at IS NULL"], []
    if flt == "open":
        where.append("done = 0")
    elif flt == "free":
        where.append("kind = 'free' AND done = 0")
    elif flt == "order":
        where.append("kind != 'free' AND done = 0")
    elif flt == "extra":
        # KHÔNG phải 5 bước mặc định của đơn: việc tự do + việc thêm trong đơn
        where.append("kind != 'order_step' AND done = 0")
    elif flt == "mine":
        # me rỗng (chưa đăng nhập) không được khớp các task chưa-phân-công ('')
        where.append("assignee = ? AND assignee != '' AND done = 0")
        params.append(me)
    elif flt == "overdue":
        where.append("done = 0 AND due_at IS NOT NULL AND due_at < ?")
        params.append(today)
    elif flt == "done":
        where.append("done = 1")
    if assignee:
        where.append("assignee = ?")
        params.append(assignee)
    w = " AND ".join(where)
    # sắp xếp: MỚI TẠO trước
    order = "ORDER BY done ASC, created_at DESC, id DESC"
    if flt == "done":
        order = "ORDER BY done_at DESC"
    conn = conn_tasks()
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM web_tasks WHERE {w}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT {COLS} FROM web_tasks WHERE {w} {order} LIMIT ? OFFSET ?",
            params + [per_page, (page - 1) * per_page],
        ).fetchall()
        return [_row(r) for r in rows], int(total)
    finally:
        conn.close()


def counts(me: str, today: str) -> dict:
    """Số cho chips: open/free/order/mine/overdue/done."""
    conn = conn_tasks()
    try:
        r = conn.execute(
            "SELECT SUM(CASE WHEN done=0 THEN 1 ELSE 0 END) open,"
            " SUM(CASE WHEN done=0 AND kind='free' THEN 1 ELSE 0 END) free,"
            " SUM(CASE WHEN done=0 AND kind!='free' THEN 1 ELSE 0 END) ord,"
            " SUM(CASE WHEN done=0 AND kind!='order_step' THEN 1 ELSE 0 END) extra,"
            " SUM(CASE WHEN done=0 AND assignee=? AND assignee!='' THEN 1 ELSE 0 END) mine,"
            " SUM(CASE WHEN done=0 AND due_at IS NOT NULL AND due_at<? THEN 1 ELSE 0 END) overdue,"
            " SUM(CASE WHEN done=1 THEN 1 ELSE 0 END) done"
            " FROM web_tasks WHERE deleted_at IS NULL", (me, today)).fetchone()
        return {"open": r["open"] or 0, "free": r["free"] or 0, "order": r["ord"] or 0,
                "extra": r["extra"] or 0,
                "mine": r["mine"] or 0, "overdue": r["overdue"] or 0, "done": r["done"] or 0}
    finally:
        conn.close()


def day_counts() -> list[dict]:
    """Đếm việc theo NGÀY HẠN cho lịch: [{d, o: chưa xong, p: đã xong}]."""
    conn = conn_tasks()
    try:
        rows = conn.execute(
            "SELECT due_at d, SUM(CASE WHEN done=0 THEN 1 ELSE 0 END) o,"
            " SUM(CASE WHEN done=1 THEN 1 ELSE 0 END) p FROM web_tasks"
            " WHERE deleted_at IS NULL AND due_at IS NOT NULL GROUP BY due_at ORDER BY due_at").fetchall()
        return [{"d": r["d"], "o": r["o"] or 0, "p": r["p"] or 0} for r in rows]
    finally:
        conn.close()


def day_tasks(day: str) -> list[dict]:
    """Mọi việc có hạn = ngày này (popup lịch)."""
    conn = conn_tasks()
    try:
        rows = conn.execute(
            f"SELECT {COLS} FROM web_tasks WHERE deleted_at IS NULL AND due_at = ? ORDER BY done ASC, created_at DESC",
            (day,)).fetchall()
        return [_row(r) for r in rows]
    finally:
        conn.close()
