"""PHIẾU ĐIỀU CHỈNH TỒN KHO 1 thùng (inventory_adjustments, app.db).

Nguyên tắc ĐÚNG LOGIC: điều chỉnh KHÔNG sửa `quantity` gốc của thùng — mỗi phiếu
= 1 dòng `box_allocations kind='adjustment'` với quantity = −delta (delta dương =
TĂNG tồn → allocation âm; delta âm = GIẢM tồn → allocation dương). Nhờ đó
`remaining = quantity − Σ allocations` tự đúng ở MỌI công thức hiện có, lịch sử
thùng bảo toàn; xoá phiếu (admin) = gỡ allocation → hoàn nguyên, có guard không
cho remaining âm. Phiếu lưu delta + old/new_remaining snapshot + lý do BẮT BUỘC.
source='manual' (sửa tay ở chi tiết thùng) | 'stocktake' (áp từ phiếu kiểm kho,
xem stocktakes.apply_stocktake). Nối: utils.db.transaction, box_allocations.
API: server_app/adjustment_routes.py.
"""
from __future__ import annotations

from utils.db import transaction

_EPS = 1e-9

_SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory_adjustments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    box_id        INTEGER NOT NULL,
    box_code      TEXT,
    product_code  TEXT,
    delta         REAL    NOT NULL,
    old_remaining REAL,
    new_remaining REAL,
    reason        TEXT    NOT NULL,
    source        TEXT    NOT NULL DEFAULT 'manual',
    stocktake_id  INTEGER,
    created_at    TEXT    DEFAULT (datetime('now', '+7 hours')),
    created_by    TEXT,
    deleted_at    TEXT,
    deleted_by    TEXT
);
"""
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_adjust_box ON inventory_adjustments(box_id)",
    "CREATE INDEX IF NOT EXISTS idx_adjust_stocktake ON inventory_adjustments(stocktake_id)",
]


def ensure_adjustments_schema(conn) -> None:
    conn.execute(_SCHEMA)
    for sql in _INDEXES:
        conn.execute(sql)


def _box_remaining(conn, box_id: int) -> tuple[dict | None, float]:
    row = conn.execute("SELECT * FROM inventory_boxes WHERE id = ?", (box_id,)).fetchone()
    if not row:
        return None, 0.0
    used = conn.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM box_allocations WHERE box_id = ?", (box_id,)
    ).fetchone()[0]
    return dict(row), float(row["quantity"] or 0) - float(used or 0)


def insert_adjustment(conn, box_id: int, *, delta: float, reason: str, by: str = "",
                      source: str = "manual", stocktake_id: int | None = None) -> tuple[dict | None, str | None]:
    """LÕI ghi 1 phiếu + allocation — KHÔNG tự mở transaction (caller bọc; transaction()
    re-entrant nên create_adjustment/apply_stocktake đều dùng được). Trả (phiếu, None)
    hoặc (None, lỗi VN)."""
    ensure_adjustments_schema(conn)
    reason = (reason or "").strip()
    if not reason:
        return None, "Bắt buộc ghi lý do điều chỉnh"
    try:
        delta = float(delta)
    except (TypeError, ValueError):
        return None, "Số điều chỉnh không hợp lệ"
    if abs(delta) < _EPS:
        return None, "Số điều chỉnh phải khác 0"
    box, old_rem = _box_remaining(conn, box_id)
    if not box:
        return None, "Không tìm thấy thùng"
    new_rem = old_rem + delta
    if new_rem < -_EPS:
        return None, f"Tồn sau điều chỉnh âm ({new_rem:g}) — thùng {box.get('box_code')} chỉ còn {old_rem:g}"
    cur = conn.execute(
        "INSERT INTO inventory_adjustments (box_id, box_code, product_code, delta, old_remaining,"
        " new_remaining, reason, source, stocktake_id, created_by)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (box_id, box.get("box_code"), box.get("product_code"), delta, old_rem, new_rem,
         reason, source, stocktake_id, by or ""))
    adj_id = cur.lastrowid
    # allocation = −delta: delta dương (tăng tồn) → dòng âm, như purchase_in/return_in
    conn.execute(
        "INSERT INTO box_allocations (box_id, order_thread_id, quantity, allocated_at, allocated_by, kind)"
        " VALUES (?,?,?,datetime('now', '+7 hours'),?, 'adjustment')",
        (box_id, adj_id, -delta, by or ""))
    return get_adjustment(conn, adj_id), None


def create_adjustment(conn, box_id: int, *, new_remaining: float, reason: str, by: str = "",
                      source: str = "manual", stocktake_id: int | None = None) -> tuple[dict | None, str | None]:
    """Điều chỉnh tay: người dùng nhập TỒN THỰC TẾ → delta tính trong CÙNG transaction
    với đọc remaining (không race với xuất/nhập đồng thời)."""
    try:
        new_remaining = float(new_remaining)
    except (TypeError, ValueError):
        return None, "Số tồn thực tế không hợp lệ"
    if new_remaining < 0:
        return None, "Tồn thực tế phải ≥ 0"
    with transaction(conn):
        ensure_adjustments_schema(conn)
        box, old_rem = _box_remaining(conn, box_id)
        if not box:
            return None, "Không tìm thấy thùng"
        delta = new_remaining - old_rem
        if abs(delta) < _EPS:
            return None, "Tồn thực tế bằng tồn hệ thống — không có gì để điều chỉnh"
        return insert_adjustment(conn, box_id, delta=delta, reason=reason, by=by,
                                 source=source, stocktake_id=stocktake_id)


def get_adjustment(conn, adj_id: int) -> dict | None:
    ensure_adjustments_schema(conn)
    r = conn.execute("SELECT * FROM inventory_adjustments WHERE id = ?", (adj_id,)).fetchone()
    return dict(r) if r else None


def list_adjustments(conn, *, box_id: int | None = None, stocktake_id: int | None = None,
                     limit: int = 100) -> list[dict]:
    """Phiếu điều chỉnh (mới → cũ), lọc theo thùng / phiếu kiểm. Gồm cả phiếu đã gỡ
    (deleted_at) để lịch sử liền mạch — client hiện gạch."""
    ensure_adjustments_schema(conn)
    where, params = [], []
    if box_id is not None:
        where.append("box_id = ?"); params.append(box_id)
    if stocktake_id is not None:
        where.append("stocktake_id = ?"); params.append(stocktake_id)
    sql = "SELECT * FROM inventory_adjustments"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def delete_adjustment(conn, adj_id: int, *, by: str = "") -> tuple[dict | None, str | None]:
    """Gỡ 1 phiếu điều chỉnh (ADMIN) = hoàn nguyên: xoá allocation 'adjustment' của
    phiếu. GUARD: phiếu từng TĂNG tồn (delta > 0) mà phần tăng đã bị dùng → gỡ sẽ
    làm remaining âm → chặn."""
    with transaction(conn):
        adj = get_adjustment(conn, adj_id)
        if not adj or adj.get("deleted_at"):
            return None, "Không tìm thấy phiếu điều chỉnh"
        # Phiếu con của một lần kiểm kho đã áp → gỡ lẻ làm sổ kiểm kho lệch với kho.
        # Muốn hoàn tác thì thao tác ở phiếu kiểm kho, không gỡ từng dòng.
        if adj.get("source") == "stocktake":
            stid = adj.get("stocktake_id")
            return None, (f"Phiếu điều chỉnh sinh từ kiểm kho #{stid} — không gỡ lẻ được "
                          "(sổ kiểm kho sẽ lệch)")
        delta = float(adj.get("delta") or 0)
        _, rem = _box_remaining(conn, int(adj["box_id"]))
        if delta > 0 and rem - delta < -_EPS:
            return None, (f"Phần tồn đã tăng ({delta:g}) đã được dùng — thùng chỉ còn {rem:g}, "
                          "gỡ phiếu sẽ làm tồn âm")
        conn.execute(
            "DELETE FROM box_allocations WHERE kind = 'adjustment' AND order_thread_id = ? AND box_id = ?",
            (adj_id, int(adj["box_id"])))
        conn.execute(
            "UPDATE inventory_adjustments SET deleted_at = datetime('now', '+7 hours'), deleted_by = ?"
            " WHERE id = ?", (by or "", adj_id))
        return adj, None
