"""PHIẾU kho đậu — nhập / xuất / điều chỉnh (`bean_slips` + `bean_moves`, app.db).

1 phiếu = 1 loại thao tác + 1 kho + nhiều dòng đậu. Ghi phiếu và các dòng biến
động trong CÙNG transaction, có guard KHÔNG cho tồn âm (lúc tạo lẫn lúc xoá).
Tồn đọc qua bean_store.stock; luật dấu ở bean_store.domain.delta_for.
"""
from __future__ import annotations

from datetime import datetime, timezone

from utils.db import transaction

from .catalog import get_bean, get_place
from .domain import KINDS, delta_for, fmt_qty, parse_qty, round_qty, today_vn
from .stock import stock_of


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_items(conn, kind: str, items) -> tuple[list[dict], str | None]:
    """Chuẩn hoá dòng phiếu: bean có thật, số hợp lệ, không trùng loại đậu."""
    if not isinstance(items, (list, tuple)) or not items:
        return [], "Phiếu cần ít nhất 1 dòng đậu"
    out: list[dict] = []
    seen: set[int] = set()
    for raw in items:
        if not isinstance(raw, dict):
            return [], "Dòng phiếu không hợp lệ"
        try:
            bean_id = int(raw.get("bean_id"))
        except (TypeError, ValueError):
            return [], "Thiếu loại đậu ở một dòng"
        bean = get_bean(conn, bean_id)
        if not bean:
            return [], f"Loại đậu #{bean_id} không tồn tại"
        if bean_id in seen:
            return [], f'Loại đậu "{bean["name"]}" bị nhập 2 dòng — gộp lại'
        seen.add(bean_id)
        qty = parse_qty(raw.get("quantity"))
        if qty is None:
            return [], f'Số lượng của "{bean["name"]}" không hợp lệ'
        if qty < 0:
            return [], f'Số lượng của "{bean["name"]}" không được âm'
        if qty == 0 and kind != "dieu_chinh":
            return [], f'Số lượng của "{bean["name"]}" phải lớn hơn 0'
        out.append({"bean_id": bean_id, "bean_name": bean["name"],
                    "quantity": qty, "note": str(raw.get("note") or "").strip()})
    return out, None


def create_slip(conn, kind: str, place_id, items, *, partner: str = "", note: str = "",
                ymd: str | None = None, by: str | None = None) -> tuple[dict | None, str | None]:
    """Tạo phiếu + các dòng biến động (1 transaction).

    kind='dieu_chinh' → `quantity` mỗi dòng là số ĐẾM THỰC TẾ, delta = đếm − tồn.
    Chặn tồn âm: xuất quá tồn / điều chỉnh về số âm đều bị từ chối.
    """
    kind = str(kind or "").strip()
    if kind not in KINDS:
        return None, "Loại phiếu không hợp lệ"
    try:
        place_id = int(place_id)
    except (TypeError, ValueError):
        return None, "Cần chọn kho"
    day = str(ymd or "").strip() or today_vn()

    with transaction(conn):
        if not get_place(conn, place_id):
            return None, "Kho không tồn tại"
        rows, err = _clean_items(conn, kind, items)
        if err:
            return None, err
        moves = []
        for it in rows:
            before = stock_of(conn, it["bean_id"], place_id)
            delta = delta_for(kind, it["quantity"], before)
            after = round_qty(before + delta)
            if after < 0:
                return None, (f'Kho không đủ "{it["bean_name"]}": còn {fmt_qty(before)}, '
                              f'xuất {fmt_qty(it["quantity"])}')
            moves.append({**it, "delta": delta, "before": before})

        cur = conn.execute(
            "INSERT INTO bean_slips (kind, place_id, partner, note, ymd, created_at, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (kind, place_id, str(partner or "").strip(), str(note or "").strip(),
             day, _now(), by or ""),
        )
        slip_id = cur.lastrowid
        for m in moves:
            conn.execute(
                "INSERT INTO bean_moves (slip_id, bean_id, place_id, delta, quantity, "
                "before_qty, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (slip_id, m["bean_id"], place_id, m["delta"], m["quantity"],
                 m["before"], m["note"]),
            )
    return get_slip(conn, slip_id), None


def get_slip(conn, slip_id) -> dict | None:
    """Phiếu + dòng đậu (kèm tên đậu/đơn vị/tên kho để hiện thẳng)."""
    row = conn.execute(
        "SELECT s.*, p.name AS place_name FROM bean_slips s "
        "LEFT JOIN bean_places p ON p.id = s.place_id "
        "WHERE s.id = ? AND s.deleted_at IS NULL", (slip_id,)
    ).fetchone()
    if not row:
        return None
    slip = dict(row)
    items = conn.execute(
        "SELECT m.*, b.name AS bean_name, b.unit AS unit FROM bean_moves m "
        "LEFT JOIN beans b ON b.id = m.bean_id WHERE m.slip_id = ? ORDER BY m.id", (slip_id,)
    ).fetchall()
    slip["items"] = [dict(i) for i in items]
    slip["total_quantity"] = round_qty(sum(abs(float(i["delta"] or 0)) for i in slip["items"]))
    return slip


def list_slips(conn, *, kind: str | None = None, place_id=None, bean_id=None,
               limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    """Phiếu mới → cũ (kèm dòng đậu). Trả (danh sách, tổng số khớp lọc)."""
    where = ["s.deleted_at IS NULL"]
    args: list = []
    if kind:
        where.append("s.kind = ?")
        args.append(kind)
    if place_id:
        where.append("s.place_id = ?")
        args.append(int(place_id))
    if bean_id:
        where.append("EXISTS (SELECT 1 FROM bean_moves m WHERE m.slip_id = s.id AND m.bean_id = ?)")
        args.append(int(bean_id))
    cond = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) c FROM bean_slips s WHERE {cond}", args).fetchone()["c"]
    rows = conn.execute(
        f"SELECT s.id FROM bean_slips s WHERE {cond} ORDER BY s.ymd DESC, s.id DESC "
        "LIMIT ? OFFSET ?", [*args, int(limit), int(offset)]
    ).fetchall()
    slips = [get_slip(conn, r["id"]) for r in rows]
    return [s for s in slips if s], int(total)


def soft_delete_slip(conn, slip_id, by: str | None = None) -> tuple[dict | None, str | None]:
    """Xoá mềm phiếu — tồn tự trả về (tồn = Σ delta phiếu CÒN SỐNG). Chặn nếu xoá
    xong tồn thành âm (đã xuất mất phần hàng của phiếu nhập này)."""
    slip = get_slip(conn, slip_id)
    if not slip:
        return None, "Không tìm thấy phiếu"
    with transaction(conn):
        for it in slip["items"]:
            after = round_qty(stock_of(conn, it["bean_id"], slip["place_id"]) - float(it["delta"] or 0))
            if after < 0:
                return None, (f'Xoá phiếu sẽ làm "{it["bean_name"]}" âm kho — '
                              "xoá các phiếu sau nó trước")
        conn.execute("UPDATE bean_slips SET deleted_at = ?, deleted_by = ? WHERE id = ?",
                     (_now(), by or "", slip_id))
    return slip, None
