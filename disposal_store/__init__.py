"""disposal_store — bảng `disposal_slips` (app.db): phiếu XUẤT HỦY hàng hóa.

1 phiếu = 1 lần hủy hàng (hư/hết hạn/vỡ…) từ 1+ thùng, BẮT BUỘC có lý do. Trừ tồn
qua `inventory_store.allocate_picks(kind='disposal')` (order_thread_id = id phiếu)
— mọi công thức remaining tự đúng; `items` JSON là snapshot hiển thị (box_code, mã
SP, số lượng lúc hủy). Xoá phiếu = admin: xoá allocations (tồn HOÀN LẠI) + xoá mềm
phiếu. Ai dùng: server_app/disposal_routes. Connection qua utils.db, 100% local —
không đụng KiotViet.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from inventory_store.allocations import allocate_picks
from utils.db import transaction

_VN_TZ = timezone(timedelta(hours=7))

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS disposal_slips (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT '',
    reason     TEXT NOT NULL DEFAULT '',
    items      TEXT NOT NULL DEFAULT '[]',
    deleted_at TEXT,
    deleted_by TEXT
)
"""


def _now() -> str:
    return datetime.now(_VN_TZ).isoformat(timespec="seconds")


def ensure_table(conn) -> None:
    conn.execute(_CREATE_SQL)


def _row_to_slip(row) -> dict:
    slip = dict(row)
    try:
        slip["items"] = json.loads(slip.get("items") or "[]")
    except (TypeError, ValueError):
        slip["items"] = []
    slip["total_quantity"] = round(sum(float(i.get("quantity") or 0) for i in slip["items"]), 3)
    return slip


def create_disposal(conn, picks, *, reason: str, by: str | None = None) -> tuple[dict | None, str | None]:
    """Tạo phiếu hủy + trừ tồn nguyên tử. picks=[{box_id, quantity?}] (quantity
    thiếu = hủy hết phần còn lại của thùng — allocate_picks kẹp theo remaining,
    bỏ qua thùng vô hiệu/hết hàng). Trả (slip, None) hoặc (None, lý do lỗi)."""
    reason = str(reason or "").strip()
    if not reason:
        return None, "Cần nhập lý do hủy"
    if not picks:
        return None, "Chưa chọn thùng nào"

    class _NoStock(Exception):
        pass

    try:
        with transaction(conn):
            cur = conn.execute(
                "INSERT INTO disposal_slips (created_at, created_by, reason, items) VALUES (?, ?, ?, ?)",
                (_now(), by or "", reason, "[]"),
            )
            slip_id = cur.lastrowid
            done = allocate_picks(conn, picks, slip_id, by=by, kind="disposal")
            if not done:
                raise _NoStock()
            conn.execute(
                "UPDATE disposal_slips SET items = ? WHERE id = ?",
                (json.dumps(done, ensure_ascii=False), slip_id),
            )
    except _NoStock:
        return None, "Thùng đã hết hàng hoặc vô hiệu — không hủy được"
    return get_disposal(conn, slip_id), None


def get_disposal(conn, slip_id) -> dict | None:
    row = conn.execute("SELECT * FROM disposal_slips WHERE id = ?", (slip_id,)).fetchone()
    return _row_to_slip(row) if row else None


def list_disposals(conn, *, limit: int = 200) -> list[dict]:
    """Phiếu hủy chưa xoá, mới nhất trước."""
    rows = conn.execute(
        "SELECT * FROM disposal_slips WHERE deleted_at IS NULL ORDER BY id DESC LIMIT ?",
        (int(limit),),
    ).fetchall()
    return [_row_to_slip(r) for r in rows]


def delete_disposal(conn, slip_id, *, by: str | None = None) -> tuple[int, str | None]:
    """Xoá phiếu (admin): xoá allocations kind='disposal' → TỒN HOÀN LẠI các thùng,
    phiếu xoá mềm giữ lịch sử. Trả (số dòng allocation đã hoàn, None) hoặc (0, lỗi)."""
    with transaction(conn):
        row = conn.execute("SELECT id, deleted_at FROM disposal_slips WHERE id = ?", (slip_id,)).fetchone()
        if not row:
            return 0, "Không tìm thấy phiếu hủy"
        if row["deleted_at"]:
            return 0, "Phiếu đã xoá rồi"
        cur = conn.execute(
            "DELETE FROM box_allocations WHERE order_thread_id = ? AND kind = 'disposal'",
            (slip_id,),
        )
        conn.execute(
            "UPDATE disposal_slips SET deleted_at = ?, deleted_by = ? WHERE id = ?",
            (_now(), by or "", slip_id),
        )
        return cur.rowcount, None
