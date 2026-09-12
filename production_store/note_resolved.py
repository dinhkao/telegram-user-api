"""ĐÁNH DẤU ĐÃ XỬ LÝ cho từng dòng cảnh báo ghi chú (production_note_resolved) — app.db.

Bảng cảnh báo ở #/sx-bang liệt kê mọi ghi chú không trùng khít câu chuẩn (xem
note_review). Văn phòng xem xong 1 dòng — sửa phụ cấp tay, thêm rule, hoặc kết luận
không cần làm gì — thì tick để nó biến khỏi danh sách, khỏi soi lại tháng sau.

Khoá = (thread_id, worker_name, note_fold): dấu bám vào ĐÚNG dòng báo cáo đó, nên thợ
ghi lại y hệt ở phiếu KHÁC vẫn cảnh báo tiếp (cố ý — mỗi phiếu là một lần trả tiền
riêng). note_fold = ghi chú đã bỏ dấu + gộp khoảng trắng (note_review._fold) để "Vít
15k" và "vít  15k" cùng là một. Nối: note_review (đọc), server_app.production_dashboard_routes.
"""
from __future__ import annotations

from utils.db import transaction

_SCHEMA = """
CREATE TABLE IF NOT EXISTS production_note_resolved (
    thread_id   INTEGER NOT NULL,
    worker_name TEXT    NOT NULL,
    note_fold   TEXT    NOT NULL,
    resolved_at TEXT    DEFAULT (datetime('now')),
    resolved_by TEXT,
    PRIMARY KEY (thread_id, worker_name, note_fold)
);
"""


def ensure_schema(conn) -> None:
    conn.execute(_SCHEMA)


def resolved_keys(conn) -> set[tuple[int, str, str]]:
    """Mọi dấu đã xử lý — dựng set 1 lần rồi tra trong vòng lặp (bảng nhỏ, vài trăm
    dòng: tick là hành động của người, không phải dữ liệu sinh tự động)."""
    ensure_schema(conn)
    return {
        (int(r[0]), str(r[1] or ""), str(r[2] or ""))
        for r in conn.execute(
            "SELECT thread_id, worker_name, note_fold FROM production_note_resolved"
        ).fetchall()
    }


def mark(conn, items: list[tuple[int, str, str]], by: str = "") -> int:
    """Đánh dấu đã xử lý. items = [(thread_id, worker_name, note_fold)]. Trả số dòng ghi."""
    if not items:
        return 0
    ensure_schema(conn)
    with transaction(conn):
        conn.executemany(
            "INSERT OR IGNORE INTO production_note_resolved "
            "(thread_id, worker_name, note_fold, resolved_by) VALUES (?,?,?,?)",
            [(int(t), str(w), str(n), by) for t, w, n in items],
        )
    return len(items)


def unmark(conn, items: list[tuple[int, str, str]]) -> int:
    """Bỏ đánh dấu (tick nhầm) — dòng quay lại danh sách cảnh báo."""
    if not items:
        return 0
    ensure_schema(conn)
    with transaction(conn):
        conn.executemany(
            "DELETE FROM production_note_resolved "
            "WHERE thread_id = ? AND worker_name = ? AND note_fold = ?",
            [(int(t), str(w), str(n)) for t, w, n in items],
        )
    return len(items)
