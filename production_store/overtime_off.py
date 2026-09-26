"""CỜ TẮT tăng ca theo (phiếu SX, thợ) — bảng production_ot_off (app.db).

Mặc định MỌI dòng được tính tăng ca theo giờ phiếu (production_store/overtime.py); văn
phòng bấm tắt cho 1 thợ ở 1 phiếu (vd thợ về sớm) → có 1 row ở đây. Bật lại = xoá row.
Khoá (thread_id, worker_name) = tên thợ như trong báo cáo phiếu, giống production_allowances
(đổi tên thợ ở worker_store.update_worker cũng đổi theo). So khớp tên không phân biệt hoa
thường. Đọc bởi report_slips.compute_range_report + server_app.production_wages. Nối: utils.db.
"""
from __future__ import annotations

from utils.db import transaction

_SCHEMA = """
CREATE TABLE IF NOT EXISTS production_ot_off (
    thread_id   INTEGER NOT NULL,
    worker_name TEXT    NOT NULL,
    off_by      TEXT,
    off_at      TEXT    DEFAULT (datetime('now')),
    UNIQUE(thread_id, worker_name)
);
"""


def ensure_schema(conn) -> None:
    conn.execute(_SCHEMA)


def _key(name) -> str:
    return str(name or "").strip().casefold()


def off_keys(conn, thread_ids) -> set:
    """{(thread_id, tên thợ đã casefold)} các dòng ĐANG TẮT tăng ca trong các phiếu cho trước."""
    tids = sorted({int(t) for t in thread_ids or []})
    if not tids:
        return set()
    qs = ",".join("?" * len(tids))
    try:
        rows = conn.execute(
            f"SELECT thread_id, worker_name FROM production_ot_off WHERE thread_id IN ({qs})", tids
        ).fetchall()
    except Exception as e:  # noqa: BLE001
        # bảng tạo LẦN ĐẦU có người bấm tắt → chưa có = chưa dòng nào tắt (đường đọc
        # không tự tạo bảng để chạy được trên kết nối chỉ-đọc); lỗi khác thì ném ra
        if "no such table" in str(e):
            return set()
        raise
    return {(int(r[0]), _key(r[1])) for r in rows}


def is_off(off: set, thread_id, worker_name) -> bool:
    return (int(thread_id), _key(worker_name)) in off


def set_ot_enabled(conn, thread_id: int, worker_name: str, on: bool, by: str = "") -> None:
    """Bật (xoá cờ) / tắt (ghi cờ) tăng ca của 1 (phiếu, thợ)."""
    name = (worker_name or "").strip()
    if not name:
        raise ValueError("thiếu tên thợ")
    ensure_schema(conn)
    with transaction(conn):
        conn.execute("DELETE FROM production_ot_off WHERE thread_id = ? AND worker_name = ? COLLATE NOCASE",
                     (int(thread_id), name))
        if not on:
            conn.execute("INSERT INTO production_ot_off (thread_id, worker_name, off_by) VALUES (?, ?, ?)",
                         (int(thread_id), name, by or ""))
