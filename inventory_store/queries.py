"""CRUD kho thùng (inventory_boxes) — IO + transaction, không chứa logic thuần.

Mọi mutation nhiều-bước bọc `transaction(conn)` (BEGIN IMMEDIATE) để 2 người
nhập/xuất cùng lúc không sinh trùng mã hoặc xuất trùng thùng. Mã thùng do
inventory_store.domain sinh. Nối: utils.db, inventory_store.domain.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta

from utils.db import transaction
from .domain import call_code, code_call_number, next_call_numbers

_VN_TZ = timezone(timedelta(hours=7))


def _now() -> str:
    return datetime.now(_VN_TZ).isoformat(timespec="seconds")


def add_boxes(conn, product_code, quantities, *, source_thread_id=None, by=None, note=None, mfg_date=None, unit_id=None, place_id=None) -> list[dict]:
    """Tạo N thùng mới cho product — SỐ GỌI 3 chữ số toàn kho, xoay vòng, nguyên tử.

    Số bị chiếm = số của thùng còn hàng hoặc vô hiệu (nhãn còn dán trên thùng thật).
    Điểm xoay = số gọi của thùng TẠO gần nhất (kể cả đã hết hàng). >999 thùng đang
    hoạt động → ValueError (caller trả lỗi). Trả list box dict."""
    code = str(product_code).strip().upper()
    created: list[dict] = []
    with transaction(conn):
        taken_rows = conn.execute(
            "SELECT b.box_code FROM inventory_boxes b WHERE b.disabled = 1 OR b.quantity > "
            "COALESCE((SELECT SUM(a.quantity) FROM box_allocations a WHERE a.box_id = b.id), 0)"
        ).fetchall()
        taken = {code_call_number(r[0]) for r in taken_rows}
        last_row = conn.execute("SELECT box_code FROM inventory_boxes ORDER BY id DESC LIMIT 1").fetchone()
        last = code_call_number(last_row[0]) if last_row else 0
        nums = next_call_numbers(last, taken, len(quantities))
        now = _now()
        for q, n in zip(quantities, nums):
            box_code = call_code(n)
            cur = conn.execute(
                "INSERT INTO inventory_boxes "
                "(product_code, box_code, quantity, status, source_thread_id, note, mfg_date, unit_id, place_id, created_at, created_by) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (code, box_code, float(q), "in_stock", source_thread_id, note or "", mfg_date or None, unit_id, place_id, now, by or ""),
            )
            created.append({
                "id": cur.lastrowid, "product_code": code, "box_code": box_code,
                "quantity": float(q), "status": "in_stock", "mfg_date": mfg_date or None,
                "source_thread_id": source_thread_id, "created_at": now, "created_by": by or "",
            })
    return created


def count_boxes_by_source(conn, source_thread_id) -> int:
    """Số thùng đã TẠO RA từ 1 phiếu SX (mọi thùng, kể cả vô hiệu). Dùng để cấm xoá phiếu."""
    row = conn.execute(
        "SELECT COUNT(*) FROM inventory_boxes WHERE source_thread_id = ?", (source_thread_id,)
    ).fetchone()
    return int(row[0]) if row else 0


def sum_boxes_by_source(conn, thread_ids) -> dict:
    """{thread_id: Σ quantity} thùng tạo từ mỗi phiếu SX — tổng 'Nhập thùng' của card/so
    sánh (CHỈ thùng nhập qua UI web, không tính số nhập tay trong numbers)."""
    ids = [int(t) for t in thread_ids if t is not None]
    if not ids:
        return {}
    q = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT source_thread_id, COALESCE(SUM(quantity), 0) FROM inventory_boxes "
        f"WHERE source_thread_id IN ({q}) GROUP BY source_thread_id", ids).fetchall()
    return {r[0]: r[1] or 0 for r in rows}


def list_boxes(conn, *, product_code=None, status=None, source_thread_id=None,
               order_thread_id=None, active_only=False) -> list[dict]:
    """Liệt kê thùng theo bộ lọc (product/status/slip nguồn/đơn). Sắp theo mã thùng.

    active_only=True → chỉ thùng còn hiệu lực (bỏ thùng bị vô hiệu) — dùng cho tồn
    kho / khả dụng phân bổ. Mặc định trả cả thùng vô hiệu (để hiển thị mờ).
    """
    where, params = [], []
    if product_code:
        where.append("b.product_code = ?"); params.append(str(product_code).strip().upper())
    if status:
        where.append("b.status = ?"); params.append(status)
    if source_thread_id is not None:
        where.append("b.source_thread_id = ?"); params.append(source_thread_id)
    if order_thread_id is not None:
        where.append("b.order_thread_id = ?"); params.append(order_thread_id)
    if active_only:
        where.append("(b.disabled IS NULL OR b.disabled = 0)")
    sql = (
        "SELECT b.*, p.name AS place_name, u.name AS unit_name, pr.unit AS product_unit, "
        "COALESCE((SELECT SUM(a.quantity) FROM box_allocations a WHERE a.box_id=b.id),0) AS allocated "
        "FROM inventory_boxes b "
        "LEFT JOIN inventory_places p ON p.id = b.place_id "
        "LEFT JOIN inventory_units u ON u.id = b.unit_id "
        "LEFT JOIN products pr ON pr.code = b.product_code"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY b.box_code"
    out = []
    for r in conn.execute(sql, params).fetchall():
        d = dict(r)
        d["remaining"] = float(d.get("quantity") or 0) - float(d.get("allocated") or 0)
        out.append(d)
    return out


def product_totals(conn, *, status="in_stock") -> list[dict]:
    """Tổng tồn + số thùng theo từng product (cho trang danh mục kho)."""
    rows = conn.execute(
        "SELECT product_code, COUNT(*) AS box_count, COALESCE(SUM(quantity),0) AS total "
        "FROM inventory_boxes WHERE status = ? GROUP BY product_code ORDER BY product_code",
        (status,),
    ).fetchall()
    return [dict(r) for r in rows]


def product_summary(conn) -> list[dict]:
    """Tồn/xuất theo product cho dashboard. Tồn = tổng CÒN LẠI (remaining) của thùng
    còn hiệu lực; đã xuất = số thùng có phần xuất; vô hiệu đếm riêng (không tính tồn)."""
    agg: dict = {}
    for b in list_boxes(conn):
        code = b["product_code"]
        g = agg.setdefault(code, {
            "product_code": code, "in_stock_total": 0.0, "in_stock_count": 0,
            "allocated_count": 0, "shipped_count": 0, "disabled_count": 0, "total_count": 0,
        })
        g["total_count"] += 1
        if b.get("disabled"):
            g["disabled_count"] += 1
        elif b["remaining"] > 0:
            g["in_stock_total"] += b["remaining"]
            g["in_stock_count"] += 1
        if (b.get("allocated") or 0) > 0:
            g["allocated_count"] += 1
    return [agg[k] for k in sorted(agg)]


def get_box(conn, box_id) -> dict | None:
    row = conn.execute(
        "SELECT b.*, p.name AS place_name, u.name AS unit_name, pr.unit AS product_unit FROM inventory_boxes b "
        "LEFT JOIN inventory_places p ON p.id = b.place_id "
        "LEFT JOIN inventory_units u ON u.id = b.unit_id "
        "LEFT JOIN products pr ON pr.code = b.product_code WHERE b.id = ?",
        (box_id,),
    ).fetchone()
    return dict(row) if row else None


def update_box(conn, box_id, *, quantity=None, note=None, mfg_date=None, place_id=None, clear_place=False, unit_id=None) -> bool:
    sets, params = [], []
    if quantity is not None:
        sets.append("quantity = ?"); params.append(float(quantity))
    if note is not None:
        sets.append("note = ?"); params.append(note)
    if mfg_date is not None:
        sets.append("mfg_date = ?"); params.append(mfg_date or None)
    if clear_place:
        sets.append("place_id = NULL")
    elif place_id is not None:
        sets.append("place_id = ?"); params.append(int(place_id))
    if unit_id is not None:
        sets.append("unit_id = ?"); params.append(int(unit_id))
    if not sets:
        return False
    params.append(box_id)
    with transaction(conn):
        conn.execute(f"UPDATE inventory_boxes SET {', '.join(sets)} WHERE id = ?", params)
    return True


# ─── Vị trí kho (inventory_places) ───────────────────────────────────────────
def list_places(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT p.id, p.name, p.note, "
        "(SELECT COUNT(*) FROM inventory_boxes b WHERE b.place_id = p.id) AS box_count "
        "FROM inventory_places p ORDER BY p.name"
    ).fetchall()
    return [dict(r) for r in rows]


def add_place(conn, name: str, note: str = "") -> dict | None:
    name = (name or "").strip()
    if not name:
        return None
    with transaction(conn):
        conn.execute("INSERT OR IGNORE INTO inventory_places (name, note) VALUES (?, ?)", (name, note or ""))
    row = conn.execute("SELECT id, name, note FROM inventory_places WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


def rename_place(conn, place_id, name: str | None = None, note: str | None = None) -> dict | None:
    """Sửa 1 vị trí kho: tên (không cho trống) và/hoặc ghi chú. Trả row sau khi đổi
    (None nếu không có gì để sửa)."""
    sets, params = [], []
    if name is not None:
        name = name.strip()
        if not name:
            return None
        sets.append("name = ?"); params.append(name)
    if note is not None:
        sets.append("note = ?"); params.append(note.strip())
    if not sets:
        return None
    with transaction(conn):
        conn.execute(f"UPDATE inventory_places SET {', '.join(sets)} WHERE id = ?", [*params, int(place_id)])
    row = conn.execute("SELECT id, name, note FROM inventory_places WHERE id = ?", (int(place_id),)).fetchone()
    return dict(row) if row else None


def delete_place(conn, place_id) -> bool:
    """Xoá 1 vị trí — thùng đang ở đó bị gỡ liên kết (place_id → NULL)."""
    with transaction(conn):
        conn.execute("UPDATE inventory_boxes SET place_id = NULL WHERE place_id = ?", (int(place_id),))
        conn.execute("DELETE FROM inventory_places WHERE id = ?", (int(place_id),))
    return True


# ─── Đơn vị chứa (inventory_units: Thùng/Bọc/Cây/Kiện/Kệ…) ────────────────────
def list_units(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT u.id, u.name, "
        "(SELECT COUNT(*) FROM inventory_boxes b WHERE b.unit_id = u.id) AS box_count "
        "FROM inventory_units u ORDER BY u.id"
    ).fetchall()
    return [dict(r) for r in rows]


def add_unit(conn, name: str) -> dict | None:
    name = (name or "").strip()
    if not name:
        return None
    with transaction(conn):
        conn.execute("INSERT OR IGNORE INTO inventory_units (name) VALUES (?)", (name,))
    row = conn.execute("SELECT id, name FROM inventory_units WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


def delete_unit(conn, unit_id) -> bool:
    """Xoá 1 đơn vị — thùng dùng nó gỡ về NULL (mặc định Thùng khi hiển thị)."""
    with transaction(conn):
        conn.execute("UPDATE inventory_boxes SET unit_id = NULL WHERE unit_id = ?", (int(unit_id),))
        conn.execute("DELETE FROM inventory_units WHERE id = ?", (int(unit_id),))
    return True


def set_disabled(conn, box_id, disabled: bool, reason: str | None = None) -> bool:
    """Vô hiệu / kích hoạt lại 1 thùng (chỉ đặt cờ + lý do). Không đụng status/đơn —
    caller phải bảo đảm thùng KHÔNG đang phân bổ đơn trước khi vô hiệu. Kích hoạt lại
    xoá lý do."""
    with transaction(conn):
        if disabled:
            conn.execute(
                "UPDATE inventory_boxes SET disabled=1, disabled_reason=? WHERE id = ?",
                (reason or "", box_id),
            )
        else:
            conn.execute(
                "UPDATE inventory_boxes SET disabled=0, disabled_reason=NULL WHERE id = ?", (box_id,)
            )
    return True


def delete_box(conn, box_id) -> bool:
    with transaction(conn):
        conn.execute("DELETE FROM inventory_boxes WHERE id = ?", (box_id,))
    return True
