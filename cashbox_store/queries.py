"""CRUD bảng cashbox_transfers — chuyển tiền tay giữa két (app.db).

Ghi/đọc thuần SQL, transaction ở đây; kiểm tra nghiệp vụ (số dư đủ, khoá két
hợp lệ) nằm ở route (server_app/cashbox_routes.py) vì cần trạng thái derive.
Kết nối: cashbox_store.schema, utils/db.py.
"""
from __future__ import annotations

import time

from utils.db import transaction

from .schema import ensure_table


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())


def _row(r) -> dict:
    return {"id": r["id"], "from_box": r["from_box"], "to_box": r["to_box"],
            "amount": r["amount"], "note": r["note"], "created_by": r["created_by"],
            "created_at": r["created_at"], "deleted_at": r["deleted_at"]}


def add_transfer(conn, from_box: str, to_box: str, amount: int, note: str, created_by: str) -> dict:
    ensure_table(conn)
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO cashbox_transfers(from_box, to_box, amount, note, created_by, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (from_box, to_box, int(amount), note or "", created_by or "", _now_iso()))
        rid = cur.lastrowid
    return get_transfer(conn, rid)


def get_transfer(conn, transfer_id: int) -> dict | None:
    ensure_table(conn)
    r = conn.execute("SELECT * FROM cashbox_transfers WHERE id=?", (transfer_id,)).fetchone()
    return _row(r) if r else None


def list_transfers(conn, include_deleted: bool = False) -> list[dict]:
    ensure_table(conn)
    sql = "SELECT * FROM cashbox_transfers"
    if not include_deleted:
        sql += " WHERE deleted_at IS NULL"
    return [_row(r) for r in conn.execute(sql + " ORDER BY id")]


def delete_transfer(conn, transfer_id: int) -> bool:
    """Xoá mềm 1 lần chuyển (admin). Trả False nếu không có/đã xoá."""
    ensure_table(conn)
    with transaction(conn):
        cur = conn.execute(
            "UPDATE cashbox_transfers SET deleted_at=? WHERE id=? AND deleted_at IS NULL",
            (_now_iso(), transfer_id))
        return cur.rowcount > 0
