"""QUY ĐỔI ĐƠN VỊ kho đậu — bảng `bean_units` (app.db).

Mỗi loại đậu có 1 đơn vị GỐC (`beans.unit` — kg/bao…) + nhiều đơn vị quy đổi:
1 row = 1 đơn vị phụ, `factor` = 1 <đơn vị phụ> bằng bao nhiêu đơn vị GỐC
(vd name='bao', factor=50 → 1 bao = 50 kg). **Mọi số trong DB (tồn, delta,
quantity) luôn theo đơn vị GỐC** — đơn vị chọn lúc nhập/xuất chỉ là cách gõ,
`bean_moves` lưu thêm snapshot (entered_qty/unit_name/unit_factor) để in lại
đúng thứ người dùng đã nhập. So tên bỏ dấu (vn_normalize) nên "Bao"/"bao" là một.
DDL ở bean_store.schema; dùng bởi bean_store.slips + server_app.bean_unit_routes.
"""
from __future__ import annotations

from utils.db import transaction
from vn import vn_normalize

from .domain import round_qty

__all__ = ["list_units", "get_unit", "add_unit", "update_unit", "delete_unit",
           "units_by_bean", "resolve_unit", "to_base"]


def list_units(conn, bean_id) -> list[dict]:
    """Đơn vị quy đổi của 1 loại đậu (KHÔNG gồm đơn vị gốc), factor to → nhỏ."""
    rows = conn.execute(
        "SELECT id, bean_id, name, factor, note FROM bean_units WHERE bean_id = ? "
        "ORDER BY factor DESC, id", (bean_id,)
    ).fetchall()
    return [{"id": int(r["id"]), "bean_id": int(r["bean_id"]), "name": r["name"],
             "factor": float(r["factor"] or 0), "note": r["note"] or ""} for r in rows]


def units_by_bean(conn) -> dict[int, list[dict]]:
    """Đơn vị của MỌI loại đậu — {bean_id: [unit…]} (1 query cho dashboard)."""
    rows = conn.execute(
        "SELECT id, bean_id, name, factor, note FROM bean_units ORDER BY factor DESC, id"
    ).fetchall()
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(int(r["bean_id"]), []).append(
            {"id": int(r["id"]), "bean_id": int(r["bean_id"]), "name": r["name"],
             "factor": float(r["factor"] or 0), "note": r["note"] or ""})
    return out


def get_unit(conn, unit_id) -> dict | None:
    row = conn.execute(
        "SELECT id, bean_id, name, factor, note FROM bean_units WHERE id = ?", (unit_id,)
    ).fetchone()
    if not row:
        return None
    return {"id": int(row["id"]), "bean_id": int(row["bean_id"]), "name": row["name"],
            "factor": float(row["factor"] or 0), "note": row["note"] or ""}


def _validate(conn, bean_id, name: str, factor, base_unit: str,
              skip_id=None) -> str | None:
    name = str(name or "").strip()
    if not name:
        return "Cần nhập tên đơn vị"
    try:
        f = float(str(factor).replace(",", "."))
    except (TypeError, ValueError):
        return "Tỉ lệ quy đổi không hợp lệ"
    if f <= 0:
        return "Tỉ lệ quy đổi phải lớn hơn 0"
    nf = vn_normalize(name)
    if nf == vn_normalize(str(base_unit or "").strip()):
        return f'"{name}" là đơn vị gốc của loại đậu này rồi'
    for u in list_units(conn, bean_id):
        if u["id"] != skip_id and vn_normalize(u["name"]) == nf:
            return f'Đơn vị "{name}" đã có rồi'
    return None


def add_unit(conn, bean_id, name: str, factor, base_unit: str,
             note: str = "", by: str | None = None) -> tuple[dict | None, str | None]:
    with transaction(conn):
        err = _validate(conn, bean_id, name, factor, base_unit)
        if err:
            return None, err
        cur = conn.execute(
            "INSERT INTO bean_units (bean_id, name, factor, note, created_by) VALUES (?, ?, ?, ?, ?)",
            (bean_id, str(name).strip(), float(str(factor).replace(",", ".")),
             str(note or "").strip(), by or ""),
        )
        unit_id = cur.lastrowid
    return get_unit(conn, unit_id), None


def update_unit(conn, unit_id, *, name: str | None = None, factor=None,
                note: str | None = None, base_unit: str = "") -> tuple[dict | None, str | None]:
    unit = get_unit(conn, unit_id)
    if not unit:
        return None, "Không tìm thấy đơn vị"
    new_name = unit["name"] if name is None else str(name).strip()
    new_factor = unit["factor"] if factor is None else factor
    with transaction(conn):
        err = _validate(conn, unit["bean_id"], new_name, new_factor, base_unit, skip_id=unit["id"])
        if err:
            return None, err
        conn.execute(
            "UPDATE bean_units SET name = ?, factor = ?, note = ? WHERE id = ?",
            (new_name, float(str(new_factor).replace(",", ".")),
             unit["note"] if note is None else str(note).strip(), unit_id),
        )
    return get_unit(conn, unit_id), None


def delete_unit(conn, unit_id) -> tuple[dict | None, str | None]:
    """Xoá hẳn 1 đơn vị quy đổi. Phiếu cũ KHÔNG hỏng: mỗi dòng phiếu đã lưu
    snapshot tên + hệ số lúc nhập, và số trong DB vốn là đơn vị gốc."""
    unit = get_unit(conn, unit_id)
    if not unit:
        return None, "Không tìm thấy đơn vị"
    with transaction(conn):
        conn.execute("DELETE FROM bean_units WHERE id = ?", (unit_id,))
    return unit, None


def resolve_unit(conn, bean_id, unit_id) -> tuple[str, float, str | None]:
    """unit_id người dùng chọn → (tên hiển thị, factor, lỗi).

    Rỗng/None/0 = ĐƠN VỊ GỐC → ('', 1.0, None) (tên rỗng = dùng beans.unit).
    """
    if unit_id in (None, "", 0, "0"):
        return "", 1.0, None
    try:
        uid = int(unit_id)
    except (TypeError, ValueError):
        return "", 1.0, "Đơn vị không hợp lệ"
    unit = get_unit(conn, uid)
    if not unit or int(unit["bean_id"]) != int(bean_id):
        return "", 1.0, "Đơn vị không thuộc loại đậu này"
    if unit["factor"] <= 0:
        return "", 1.0, "Tỉ lệ quy đổi của đơn vị không hợp lệ"
    return unit["name"], unit["factor"], None


def to_base(qty: float, factor: float) -> float:
    """Số theo đơn vị đã chọn → số theo ĐƠN VỊ GỐC (mọi thứ trong DB là gốc)."""
    return round_qty(float(qty or 0) * float(factor or 1))
