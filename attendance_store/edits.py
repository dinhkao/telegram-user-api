"""Lớp HIỆU CHỈNH giờ chấm công (app.db) — sửa tay KHÔNG đụng bảng raw.

`attendance_events` là dữ liệu máy, bất biến (collector gửi lại bất kỳ lúc nào —
INSERT OR IGNORE theo event_id). Văn phòng sửa qua 2 bảng phủ lên:
- attendance_manual: giờ chấm THÊM TAY (employee_code, ymd, hhmm, ai thêm);
- attendance_suppressed: ẨN 1 event máy theo event_id (sửa 1 giờ = ẩn giờ máy +
  thêm giờ tay).
Hiển thị = (giờ máy − đã ẩn) ∪ giờ tay (merge ở store.day_summary) ⇒ batch mới của
máy không bao giờ đè phần đã sửa. Nối: utils.db; dùng bởi attendance_store.store +
server_app/attendance_routes.
"""
from __future__ import annotations

import re

from utils.db import transaction

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_YMD = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS attendance_manual (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_code TEXT NOT NULL,
    ymd           TEXT NOT NULL,          -- 'YYYY-MM-DD'
    hhmm          TEXT NOT NULL,          -- 'HH:MM'
    created_by    TEXT DEFAULT '',
    created_at    TEXT DEFAULT (datetime('now', '+7 hours'))
);
CREATE TABLE IF NOT EXISTS attendance_suppressed (
    event_id      TEXT PRIMARY KEY,       -- → attendance_events.event_id (ẩn khỏi hiển thị)
    created_by    TEXT DEFAULT '',
    created_at    TEXT DEFAULT (datetime('now', '+7 hours'))
);
"""
_IDX = "CREATE INDEX IF NOT EXISTS idx_att_manual_day ON attendance_manual(ymd, employee_code)"


def ensure_edit_schema(conn) -> None:
    conn.executescript(_SCHEMA)
    conn.execute(_IDX)
    conn.commit()


def add_manual(conn, employee_code: str, ymd: str, hhmm: str, by: str = "") -> int:
    code = (employee_code or "").strip()
    if not code:
        raise ValueError("thiếu employee_code")
    if not _YMD.match(ymd or ""):
        raise ValueError("ngày phải dạng YYYY-MM-DD")
    if not _HHMM.match(hhmm or ""):
        raise ValueError("giờ phải dạng HH:MM")
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO attendance_manual (employee_code, ymd, hhmm, created_by) VALUES (?,?,?,?)",
            (code, ymd, hhmm, by))
        return cur.lastrowid


def delete_manual(conn, manual_id: int) -> bool:
    with transaction(conn):
        cur = conn.execute("DELETE FROM attendance_manual WHERE id = ?", (int(manual_id),))
        return cur.rowcount > 0


def set_suppressed(conn, event_id: str, on: bool, by: str = "") -> None:
    """Ẩn/hiện 1 giờ chấm MÁY. Chỉ nhận event_id có thật (chống rác)."""
    with transaction(conn):
        row = conn.execute("SELECT 1 FROM attendance_events WHERE event_id = ?", (event_id,)).fetchone()
        if not row:
            raise ValueError("event_id không tồn tại")
        if on:
            conn.execute(
                "INSERT INTO attendance_suppressed (event_id, created_by) VALUES (?, ?)"
                " ON CONFLICT(event_id) DO NOTHING", (event_id, by))
        else:
            conn.execute("DELETE FROM attendance_suppressed WHERE event_id = ?", (event_id,))


def day_detail(conn, employee_code: str, ymd: str) -> dict:
    """Toàn bộ giờ chấm 1 (NV, ngày) cho popup sửa: máy (kèm cờ ẩn) + tay."""
    machine = conn.execute(
        "SELECT e.event_id, substr(e.occurred_at, 12, 5), s.event_id IS NOT NULL"
        " FROM attendance_events e LEFT JOIN attendance_suppressed s ON s.event_id = e.event_id"
        " WHERE e.employee_code = ? AND e.occurred_ymd = ? ORDER BY e.occurred_at",
        (employee_code, ymd)).fetchall()
    manual = conn.execute(
        "SELECT id, hhmm, created_by, created_at FROM attendance_manual"
        " WHERE employee_code = ? AND ymd = ? ORDER BY hhmm",
        (employee_code, ymd)).fetchall()
    return {
        "machine": [{"event_id": r[0], "time": r[1], "suppressed": bool(r[2])} for r in machine],
        "manual": [{"id": r[0], "time": r[1], "created_by": r[2], "created_at": r[3]} for r in manual],
    }


def month_edits(conn, ym: str) -> tuple[list[tuple], set]:
    """Cho merge tháng: (dòng tay [(code, ymd, hhmm)], set event_id đã ẩn)."""
    manual = conn.execute(
        "SELECT employee_code, ymd, hhmm FROM attendance_manual WHERE ymd LIKE ? || '-%'",
        (ym,)).fetchall()
    suppressed = {r[0] for r in conn.execute("SELECT event_id FROM attendance_suppressed").fetchall()}
    return list(manual), suppressed
