"""QUY ĐỔI ĐƠN VỊ hàng hoá — bảng product_units (app.db) + VAI đơn vị.

1 SP có 1 đơn vị GỐC (products.unit — cây/kg/gói…) + nhiều đơn vị quy đổi:
1 row = 1 đơn vị phụ, `factor` = 1 <đơn vị phụ> bằng bao nhiêu đơn vị gốc
(vd unit='thùng', factor=30 → 1 thùng = 30 cây). Quy đổi giữa 2 đơn vị bất kỳ
= tỉ số factor (gốc có factor 1). Khoá theo products.id (đổi mã SP không ảnh
hưởng). VAI đơn vị (2026-07-17, docs/plan-don-vi-hang-hoa.md): mỗi SP chỉ định
tối đa 1 đơn vị/vai qua 3 cột products.{bulk,display,stocktake}_unit_id
(NULL = không · 0 = đơn vị gốc · >0 = product_units.id) — resolve qua unit_role.
Nối: utils.db (qua conn của caller), products. API:
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


def delete_unit(conn, product_id: int, unit_id: int) -> tuple[dict | None, str | None]:
    """Xoá 1 đơn vị quy đổi → (row đã xoá, None) hoặc (None, lỗi).
    CHẶN xoá khi đơn vị đang giữ VAI (nguyên kiện/hiển thị/kiểm kho) — gỡ vai trước."""
    ensure_schema(conn)
    row = conn.execute(
        "SELECT id, name, factor FROM product_units WHERE id = ? AND product_id = ?",
        (unit_id, product_id),
    ).fetchone()
    if not row:
        return None, "Không tìm thấy đơn vị"
    held = [label for col, label in (("bulk_unit_id", "nguyên kiện"), ("display_unit_id", "hiển thị"),
                                     ("stocktake_unit_id", "kiểm kho"))
            if _role_value(conn, product_id, col) == int(unit_id)]
    if held:
        return None, f"Đơn vị '{row[1]}' đang được chỉ định làm đơn vị {' + '.join(held)} — gỡ vai trước rồi xoá"
    conn.execute("DELETE FROM product_units WHERE id = ?", (unit_id,))
    conn.commit()
    return {"id": row[0], "name": row[1], "factor": float(row[2] or 0)}, None


# ─── VAI đơn vị (bulk = 📦 nguyên kiện · display = 👁 hiển thị · stocktake = 📋 kiểm kho) ──
ROLES = ("bulk", "display", "stocktake")


def _role_value(conn, product_id: int, col: str):
    r = conn.execute(f"SELECT {col} FROM products WHERE id = ?", (product_id,)).fetchone()
    return None if not r or r[0] is None else int(r[0])


def unit_role(product: dict, units: list[dict], role: str) -> dict | None:
    """THUẦN: resolve vai `role` của SP → {id, name, factor} hoặc None.
    Quy ước: NULL = không chỉ định · 0 = đơn vị GỐC (factor 1) · >0 = product_units.id.
    `units` = list_units của SP; đơn vị đã mất (không nên xảy ra — xoá bị chặn) → None."""
    rid = product.get(f"{role}_unit_id")
    if rid is None:
        return None
    rid = int(rid)
    if rid == 0:
        return {"id": 0, "name": (product.get("unit") or "cây").strip() or "cây", "factor": 1.0}
    for u in units:
        if int(u["id"]) == rid:
            return {"id": rid, "name": u["name"], "factor": float(u["factor"] or 0)}
    return None


def resolve_roles(conn, product: dict) -> dict:
    """Resolve cả 3 vai cho payload: {bulk_unit, display_unit, stocktake_unit}."""
    units = list_units(conn, int(product["id"]))
    return {f"{r}_unit": unit_role(product, units, r) for r in ROLES}


def validate_role_value(conn, product_id: int, value) -> str | None:
    """Kiểm giá trị vai từ API: None/0 luôn hợp lệ; >0 phải là đơn vị của đúng SP."""
    if value is None:
        return None
    try:
        v = int(value)
    except (TypeError, ValueError):
        return "Giá trị vai đơn vị không hợp lệ"
    if v == 0:
        return None
    if any(int(u["id"]) == v for u in list_units(conn, product_id)):
        return None
    return "Đơn vị không thuộc sản phẩm này"


def convert(qty: float, from_factor: float, to_factor: float) -> float:
    """THUẦN: đổi qty từ đơn vị có from_factor sang đơn vị có to_factor
    (factor = số đơn vị gốc / 1 đơn vị đó; đơn vị gốc = 1)."""
    if to_factor <= 0:
        raise ValueError("to_factor phải > 0")
    return qty * from_factor / to_factor
