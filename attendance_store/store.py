"""Bảng attendance_events + attendance_employee_map (app.db): lưu raw punch idempotent,
map mã NV máy chấm công → thợ. Nối: utils.db; đọc bởi server_app/attendance_routes.
"""
from __future__ import annotations

import json

from utils.db import transaction

_SCHEMA = """
CREATE TABLE IF NOT EXISTS attendance_events (
    event_id        TEXT    PRIMARY KEY,       -- SHA-256 từ collector (idempotency)
    machine_id      TEXT    NOT NULL,
    employee_code   TEXT    NOT NULL,          -- mã NV TRÊN MÁY chấm công (string)
    worker_id       INTEGER,                   -- → production_workers.id (NULL = chưa map)
    occurred_at     TEXT    NOT NULL,          -- giờ chấm thật ISO +07:00 (payroll dùng)
    occurred_ymd    TEXT    NOT NULL,          -- 'YYYY-MM-DD' theo giờ máy (nhóm theo ngày)
    source_timezone TEXT    NOT NULL DEFAULT '',
    verify_mode     INTEGER NOT NULL DEFAULT 0,
    in_out_mode     INTEGER NOT NULL DEFAULT 0,
    work_code       INTEGER NOT NULL DEFAULT 0,
    source_index    INTEGER NOT NULL DEFAULT 0,
    collected_at    TEXT    DEFAULT '',        -- UTC lúc collector đọc (KHÔNG phải giờ chấm)
    received_at     TEXT    DEFAULT (datetime('now', '+7 hours')),
    raw_payload     TEXT    NOT NULL           -- event JSON nguyên bản
);
CREATE TABLE IF NOT EXISTS attendance_employee_map (
    employee_code   TEXT    PRIMARY KEY,
    worker_id       INTEGER NOT NULL,          -- → production_workers.id
    updated_by      TEXT    DEFAULT '',
    updated_at      TEXT    DEFAULT (datetime('now', '+7 hours'))
);
"""
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_attendance_emp_time ON attendance_events(employee_code, occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_attendance_ymd ON attendance_events(occurred_ymd)",
]


def ensure_schema(conn) -> None:
    conn.executescript(_SCHEMA)
    for sql in _INDEXES:
        conn.execute(sql)
    conn.commit()


def insert_events(conn, events: list[dict]) -> dict:
    """Ghi batch ĐÃ VALIDATE trong 1 transaction. Trùng event_id → bỏ qua êm
    (INSERT OR IGNORE — retry của collector là bình thường). Trả
    {accepted, duplicates} — accepted = số dòng MỚI."""
    inserted = 0
    with transaction(conn):
        mapping = dict(conn.execute(
            "SELECT employee_code, worker_id FROM attendance_employee_map").fetchall())
        for ev in events:
            cur = conn.execute(
                "INSERT OR IGNORE INTO attendance_events (event_id, machine_id, employee_code,"
                " worker_id, occurred_at, occurred_ymd, source_timezone, verify_mode,"
                " in_out_mode, work_code, source_index, collected_at, raw_payload)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ev["event_id"], ev["machine_id"], ev["employee_code"].strip(),
                 mapping.get(ev["employee_code"].strip()),
                 ev["occurred_at"], ev["occurred_ymd"], ev.get("timezone") or "",
                 int(ev.get("verify_mode", 0)), int(ev.get("in_out_mode", 0)),
                 int(ev.get("work_code", 0)), int(ev.get("source_index", 0)),
                 ev.get("collected_at") or "",
                 json.dumps(ev, ensure_ascii=False)))
            inserted += cur.rowcount
    return {"accepted": inserted, "duplicates": len(events) - inserted}


def _row_to_event(r) -> dict:
    return {
        "event_id": r[0], "machine_id": r[1], "employee_code": r[2],
        "worker_id": r[3], "worker_name": r[13], "occurred_at": r[4],
        "occurred_ymd": r[5], "verify_mode": r[7], "in_out_mode": r[8],
        "work_code": r[9], "received_at": r[12],
    }


_SELECT = ("SELECT e.event_id, e.machine_id, e.employee_code, e.worker_id, e.occurred_at,"
           " e.occurred_ymd, e.source_timezone, e.verify_mode, e.in_out_mode, e.work_code,"
           " e.source_index, e.collected_at, e.received_at, w.name"
           " FROM attendance_events e LEFT JOIN production_workers w ON w.id = e.worker_id")


def list_events(conn, *, day: str | None = None, employee_code: str | None = None,
                worker_id: int | None = None, limit: int = 500) -> list[dict]:
    """Punch theo ngày/NV, mới nhất trước (xem trên web — office)."""
    where, params = [], []
    if day:
        where.append("e.occurred_ymd = ?"); params.append(day)
    if employee_code:
        where.append("e.employee_code = ?"); params.append(employee_code)
    if worker_id is not None:
        where.append("e.worker_id = ?"); params.append(worker_id)
    sql = _SELECT + ((" WHERE " + " AND ".join(where)) if where else "")
    sql += " ORDER BY e.occurred_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 2000)))
    return [_row_to_event(r) for r in conn.execute(sql, params).fetchall()]


def day_summary(conn, ym: str) -> list[dict]:
    """Mỗi (ngày, NV) trong tháng 'YYYY-MM': số lần chấm + giờ đầu/cuối."""
    rows = conn.execute(
        "SELECT e.occurred_ymd, e.employee_code, e.worker_id, w.name, COUNT(*),"
        " MIN(e.occurred_at), MAX(e.occurred_at)"
        " FROM attendance_events e LEFT JOIN production_workers w ON w.id = e.worker_id"
        " WHERE e.occurred_ymd LIKE ? || '-%'"
        " GROUP BY e.occurred_ymd, e.employee_code ORDER BY e.occurred_ymd DESC, e.employee_code",
        (ym,)).fetchall()
    return [{"day": r[0], "employee_code": r[1], "worker_id": r[2], "worker_name": r[3],
             "punches": r[4], "first": r[5], "last": r[6]} for r in rows]


def list_mappings(conn) -> list[dict]:
    """Mọi map mã NV máy → thợ (hiện ở chi tiết thợ + dashboard chấm công)."""
    rows = conn.execute(
        "SELECT m.employee_code, m.worker_id, w.name FROM attendance_employee_map m"
        " LEFT JOIN production_workers w ON w.id = m.worker_id ORDER BY m.employee_code"
    ).fetchall()
    return [{"employee_code": r[0], "worker_id": r[1], "worker_name": r[2]} for r in rows]


def unmapped_codes(conn) -> list[dict]:
    """Hàng chờ review: employee_code chưa map → thợ, kèm số punch + lần gần nhất."""
    rows = conn.execute(
        "SELECT employee_code, COUNT(*), MAX(occurred_at) FROM attendance_events"
        " WHERE worker_id IS NULL GROUP BY employee_code ORDER BY MAX(occurred_at) DESC"
    ).fetchall()
    return [{"employee_code": r[0], "punches": r[1], "last": r[2]} for r in rows]


def map_employee_code(conn, employee_code: str, worker_id: int | None, by: str = "") -> int:
    """Gán/gỡ map mã NV → thợ + BACKFILL mọi event cũ của mã đó. Trả số event cập nhật.
    worker_id None = gỡ map (event về hàng chờ)."""
    code = employee_code.strip()
    with transaction(conn):
        if worker_id is None:
            conn.execute("DELETE FROM attendance_employee_map WHERE employee_code = ?", (code,))
        else:
            conn.execute(
                "INSERT INTO attendance_employee_map (employee_code, worker_id, updated_by,"
                " updated_at) VALUES (?,?,?, datetime('now','+7 hours'))"
                " ON CONFLICT(employee_code) DO UPDATE SET worker_id=excluded.worker_id,"
                " updated_by=excluded.updated_by, updated_at=excluded.updated_at",
                (code, int(worker_id), by))
        cur = conn.execute("UPDATE attendance_events SET worker_id = ? WHERE employee_code = ?",
                           (worker_id, code))
        return cur.rowcount
