"""NHÀ CUNG CẤP (suppliers, app.db) — sổ nhà cung cấp cho phiếu nhập hàng.

100% local, KHÔNG dính KiotViet. Mỗi NCC: tên + SĐT + địa chỉ + ghi chú, xoá mềm.
Dashboard kèm thống kê từ purchase_slips (số phiếu, tổng tiền, lần nhập cuối).
Nối: utils.db, purchase_store (JOIN thống kê). API: server_app/supplier_routes.py.
"""
from __future__ import annotations

_SCHEMA = """
CREATE TABLE IF NOT EXISTS suppliers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    phone       TEXT,
    address     TEXT,
    note        TEXT,
    created_by  TEXT,
    created_at  TEXT DEFAULT (datetime('now', '+7 hours')),
    deleted_at  TEXT,
    deleted_by  TEXT
);
"""


def ensure_suppliers_schema(conn) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


def add_supplier(conn, name: str, *, phone: str = "", address: str = "",
                 note: str = "", by: str = "") -> dict:
    ensure_suppliers_schema(conn)
    cur = conn.execute(
        "INSERT INTO suppliers (name, phone, address, note, created_by) VALUES (?,?,?,?,?)",
        (name.strip(), phone or "", address or "", note or "", by or ""))
    conn.commit()
    return get_supplier(conn, cur.lastrowid)


def get_supplier(conn, supplier_id: int) -> dict | None:
    ensure_suppliers_schema(conn)
    r = conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
    return dict(r) if r else None


def update_supplier(conn, supplier_id: int, *, name=None, phone=None,
                    address=None, note=None) -> bool:
    """Sửa từng ô — chỉ ô nào truyền vào (không None) mới UPDATE."""
    ensure_suppliers_schema(conn)
    sets, vals = [], []
    for col, v in (("name", name), ("phone", phone), ("address", address), ("note", note)):
        if v is not None:
            sets.append(f"{col} = ?")
            vals.append(str(v).strip() if col == "name" else str(v))
    if not sets:
        return False
    vals.append(supplier_id)
    conn.execute(f"UPDATE suppliers SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()
    return True


def list_suppliers(conn, include_deleted: bool = False) -> list[dict]:
    """Danh sách NCC kèm thống kê phiếu nhập (số phiếu, tổng tiền, lần nhập cuối)."""
    ensure_suppliers_schema(conn)
    from purchase_store import ensure_purchases_schema
    ensure_purchases_schema(conn)
    where = "" if include_deleted else "WHERE s.deleted_at IS NULL"
    rows = conn.execute(
        f"""SELECT s.*, COUNT(p.id) AS so_phieu,
                   COALESCE(SUM(p.total), 0) AS tong_tien,
                   MAX(p.created_at) AS last_at
            FROM suppliers s
            LEFT JOIN purchase_slips p ON p.supplier_id = s.id AND p.deleted_at IS NULL
            {where} GROUP BY s.id ORDER BY s.name COLLATE NOCASE""").fetchall()
    return [dict(r) for r in rows]


def soft_delete_supplier(conn, supplier_id: int, by: str = "") -> bool:
    ensure_suppliers_schema(conn)
    conn.execute(
        "UPDATE suppliers SET deleted_at = datetime('now', '+7 hours'), deleted_by = ?"
        " WHERE id = ? AND deleted_at IS NULL", (by or "", supplier_id))
    conn.commit()
    return True
