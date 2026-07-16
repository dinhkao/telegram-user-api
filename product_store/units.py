"""QUY ĐỔI ĐƠN VỊ hàng hoá — bảng product_units (app.db).

1 SP có 1 đơn vị GỐC (products.unit — cây/kg/gói…) + nhiều đơn vị quy đổi:
1 row = 1 đơn vị phụ, `factor` = 1 <đơn vị phụ> bằng bao nhiêu đơn vị gốc
(vd unit='thùng', factor=30 → 1 thùng = 30 cây). Quy đổi giữa 2 đơn vị bất kỳ
= tỉ số factor (gốc có factor 1). Khoá theo products.id (đổi mã SP không ảnh
hưởng). Nối: utils.db (qua conn của caller), products. API:
server_app/product_unit_routes.py; UI: webapp detail/ProductUnits.tsx.
"""
from __future__ import annotations

from vn import vn_normalize

_SCHEMA = """
CREATE TABLE IF NOT EXISTS product_units (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    name       TEXT    NOT NULL,
    factor     REAL    NOT NULL,
    note       TEXT    DEFAULT '',
    created_at TEXT    DEFAULT (datetime('now'))
);
"""
_INDEX = "CREATE INDEX IF NOT EXISTS idx_punits_product ON product_units(product_id)"


def ensure_schema(conn) -> None:
    conn.execute(_SCHEMA)
    conn.execute(_INDEX)


def list_units(conn, product_id: int) -> list[dict]:
    """Các đơn vị quy đổi của 1 SP (không gồm đơn vị gốc), factor to → nhỏ."""
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT id, name, factor, note FROM product_units WHERE product_id = ? ORDER BY factor DESC, id",
        (product_id,),
    ).fetchall()
    return [{"id": r[0], "name": r[1], "factor": float(r[2] or 0), "note": r[3] or ""} for r in rows]


def _validate(conn, product_id: int, name: str, factor, base_unit: str, skip_id: int | None = None) -> str | None:
    """Trả thông báo lỗi (VN) hoặc None nếu hợp lệ. So tên bỏ dấu, không phân biệt hoa thường."""
    name = (name or "").strip()
    if not name:
        return "Thiếu tên đơn vị"
    try:
        f = float(factor)
    except (TypeError, ValueError):
        return "Tỉ lệ quy đổi không hợp lệ"
    if f <= 0:
        return "Tỉ lệ quy đổi phải > 0"
    nf = vn_normalize(name)
    if nf == vn_normalize((base_unit or "").strip() or "cây"):
        return f"'{name}' là đơn vị gốc của SP rồi"
    for u in list_units(conn, product_id):
        if u["id"] != skip_id and vn_normalize(u["name"]) == nf:
            return f"Đơn vị '{name}' đã có rồi"
    return None


def add_unit(conn, product_id: int, name: str, factor, base_unit: str) -> tuple[dict | None, str | None]:
    """Thêm 1 đơn vị quy đổi → (unit, None) hoặc (None, lỗi)."""
    err = _validate(conn, product_id, name, factor, base_unit)
    if err:
        return None, err
    cur = conn.execute(
        "INSERT INTO product_units (product_id, name, factor) VALUES (?, ?, ?)",
        (product_id, name.strip(), float(factor)),
    )
    conn.commit()
    return {"id": cur.lastrowid, "name": name.strip(), "factor": float(factor), "note": ""}, None


def update_unit(conn, product_id: int, unit_id: int, name: str, factor, base_unit: str) -> tuple[dict | None, str | None]:
    """Sửa tên/tỉ lệ 1 đơn vị quy đổi."""
    err = _validate(conn, product_id, name, factor, base_unit, skip_id=unit_id)
    if err:
        return None, err
    cur = conn.execute(
        "UPDATE product_units SET name = ?, factor = ? WHERE id = ? AND product_id = ?",
        (name.strip(), float(factor), unit_id, product_id),
    )
    conn.commit()
    if cur.rowcount == 0:
        return None, "Không tìm thấy đơn vị"
    return {"id": unit_id, "name": name.strip(), "factor": float(factor)}, None


def delete_unit(conn, product_id: int, unit_id: int) -> dict | None:
    """Xoá 1 đơn vị quy đổi; trả row đã xoá (cho audit) hoặc None."""
    ensure_schema(conn)
    row = conn.execute(
        "SELECT id, name, factor FROM product_units WHERE id = ? AND product_id = ?",
        (unit_id, product_id),
    ).fetchone()
    if not row:
        return None
    conn.execute("DELETE FROM product_units WHERE id = ?", (unit_id,))
    conn.commit()
    return {"id": row[0], "name": row[1], "factor": float(row[2] or 0)}


def convert(qty: float, from_factor: float, to_factor: float) -> float:
    """THUẦN: đổi qty từ đơn vị có from_factor sang đơn vị có to_factor
    (factor = số đơn vị gốc / 1 đơn vị đó; đơn vị gốc = 1)."""
    if to_factor <= 0:
        raise ValueError("to_factor phải > 0")
    return qty * from_factor / to_factor
