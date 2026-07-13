"""usage_store — bảng `usage_stats` (app.db): đếm GỘP thao tác webapp theo ngày.

1 row = (ngày, user, kind view/tap, trang chuẩn hoá, nhãn nút) với count CỘNG DỒN —
không log thô từng cú bấm (tránh phình DB kiểu audit_events). Client gom buffer 20s
mới gửi 1 batch (webapp/src/usage.ts). Ai dùng: server_app/usage_routes.
Connection qua utils.db (cổng chung).
"""
from __future__ import annotations

import datetime
from typing import Any

from utils.db import get_connection, transaction

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS usage_stats (
    day TEXT NOT NULL,
    username TEXT NOT NULL,
    kind TEXT NOT NULL,
    page TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, username, kind, page, label)
)
"""

_ensured: set[str] = set()  # DDL 1 lần mỗi path mỗi process
_KINDS = {"view", "tap"}
MAX_EVENTS = 200  # trần 1 batch — client gom 20s, vượt trần là dữ liệu rác


def _conn(path: str | None = None):
    conn = get_connection(path) if path else get_connection()
    key = path or ""
    if key not in _ensured:
        conn.execute(_CREATE_SQL)
        _ensured.add(key)
    return conn


def _clean(events: list[Any]) -> list[tuple[str, str, str, int]]:
    """Lọc/cắt event từ client (không tin dữ liệu ngoài): kind hợp lệ, page bắt
    buộc, nhãn ≤64, n 1..1000."""
    out: list[tuple[str, str, str, int]] = []
    for event in events[:MAX_EVENTS]:
        if not isinstance(event, dict):
            continue
        kind = str(event.get("kind") or "")
        page = str(event.get("page") or "").strip()[:48]
        label = str(event.get("label") or "").strip()[:64]
        try:
            n = int(event.get("n", 1))
        except (TypeError, ValueError):
            continue
        if kind not in _KINDS or not page or n <= 0:
            continue
        out.append((kind, page, label, min(n, 1000)))
    return out


def record_batch(username: str, events: list[Any], *, day: str | None = None, db_path: str | None = None) -> int:
    """Cộng dồn 1 batch event vào ngày `day` (mặc định hôm nay — server chạy giờ VN).
    Trả về số event đã ghi."""
    rows = _clean(list(events or []))
    if not rows:
        return 0
    day = day or datetime.date.today().isoformat()
    username = str(username or "?")[:32]
    conn = _conn(db_path)
    try:
        with transaction(conn):
            conn.executemany(
                "INSERT INTO usage_stats (day, username, kind, page, label, count) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(day, username, kind, page, label) DO UPDATE SET count = count + excluded.count",
                [(day, username, kind, page, label, n) for kind, page, label, n in rows],
            )
        return len(rows)
    finally:
        conn.close()


def stats(days: int = 30, *, username: str | None = None, db_path: str | None = None) -> dict:
    """Tổng hợp `days` ngày gần nhất (lọc 1 user nếu truyền): theo trang, theo nhãn
    nút (chỉ tap), theo user. Sắp giảm dần — đầu danh sách = dùng nhiều, cuối = ít."""
    days = max(1, min(int(days or 30), 365))
    cutoff = (datetime.date.today() - datetime.timedelta(days=days - 1)).isoformat()
    where, params = "day >= ?", [cutoff]
    if username:
        where += " AND username = ?"
        params.append(username)
    conn = _conn(db_path)
    try:
        pages = conn.execute(
            f"SELECT page, SUM(CASE WHEN kind='view' THEN count ELSE 0 END) AS views, "
            f"SUM(CASE WHEN kind='tap' THEN count ELSE 0 END) AS taps "
            f"FROM usage_stats WHERE {where} GROUP BY page ORDER BY views + taps DESC",
            params,
        ).fetchall()
        labels = conn.execute(
            f"SELECT page, label, SUM(count) AS count FROM usage_stats "
            f"WHERE {where} AND kind = 'tap' AND label != '' GROUP BY page, label ORDER BY count DESC",
            params,
        ).fetchall()
        users = conn.execute(
            f"SELECT username, SUM(CASE WHEN kind='view' THEN count ELSE 0 END) AS views, "
            f"SUM(CASE WHEN kind='tap' THEN count ELSE 0 END) AS taps "
            f"FROM usage_stats WHERE {where} GROUP BY username ORDER BY taps DESC",
            params,
        ).fetchall()
        return {
            "days": days, "since": cutoff,
            "pages": [dict(r) for r in pages],
            "labels": [dict(r) for r in labels],
            "users": [dict(r) for r in users],
        }
    finally:
        conn.close()
