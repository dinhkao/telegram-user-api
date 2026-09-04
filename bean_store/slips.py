"""PHIẾU kho đậu — nhập / xuất / điều chỉnh / chuyển kho (`bean_slips` + `bean_moves`).

1 phiếu = 1 loại thao tác + 1 kho + nhiều dòng đậu. Riêng kind='chuyen' có thêm
KHO ĐÍCH (`dest_place_id`): mỗi dòng đậu ghi 2 bút toán −q/+q nên tồn tổng bảo
toàn. Ghi phiếu và các dòng biến động trong CÙNG transaction, có guard KHÔNG cho
tồn âm (lúc tạo lẫn lúc xoá). Tồn đọc qua bean_store.stock; luật dấu ở
bean_store.domain.delta_for.
"""
from __future__ import annotations

from datetime import datetime, timezone

from utils.db import transaction

from .catalog import get_bean, get_place
from .domain import KINDS, delta_for, fmt_qty, parse_qty, round_qty, today_vn
from .stock import stock_of
from .units import resolve_unit, to_base


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_items(conn, kind: str, items) -> tuple[list[dict], str | None]:
    """Chuẩn hoá dòng phiếu: bean có thật, số hợp lệ, không trùng loại đậu.

    `unit_id` (tuỳ chọn) = đơn vị quy đổi người dùng chọn — số gõ vào được ĐỔI VỀ
    ĐƠN VỊ GỐC ngay ở đây (`quantity`), số gõ giữ lại ở `entered_qty` để in lại.
    """
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
        unit_name, factor, uerr = resolve_unit(conn, bean_id, raw.get("unit_id"))
        if uerr:
            return [], f'{uerr} ("{bean["name"]}")'
        out.append({"bean_id": bean_id, "bean_name": bean["name"],
                    "base_unit": bean["unit"] or "",
                    "quantity": to_base(qty, factor),   # DB luôn theo đơn vị GỐC
                    "entered_qty": qty, "unit_name": unit_name, "unit_factor": factor,
                    "note": str(raw.get("note") or "").strip()})
    return out, None


def create_slip(conn, kind: str, place_id, items, *, dest_place_id=None,
                partner: str = "", note: str = "",
                ymd: str | None = None, by: str | None = None) -> tuple[dict | None, str | None]:
    """Tạo phiếu + các dòng biến động (1 transaction).

    kind='dieu_chinh' → `quantity` mỗi dòng là số ĐẾM THỰC TẾ, delta = đếm − tồn.
    kind='chuyen' → cần thêm `dest_place_id` (kho đích ≠ kho nguồn); mỗi dòng ghi
    2 bút toán −q kho nguồn / +q kho đích. Chặn tồn âm: xuất/chuyển quá tồn /
    điều chỉnh về số âm đều bị từ chối.
    """
    kind = str(kind or "").strip()
    if kind not in KINDS:
        return None, "Loại phiếu không hợp lệ"
    try:
        place_id = int(place_id)
    except (TypeError, ValueError):
        return None, "Cần chọn kho"
    if kind == "chuyen":
        try:
            dest_place_id = int(dest_place_id)
        except (TypeError, ValueError):
            return None, "Cần chọn kho đích để chuyển đến"
        if dest_place_id == place_id:
            return None, "Kho đích phải khác kho nguồn"
    else:
        dest_place_id = None
    day = str(ymd or "").strip() or today_vn()

    with transaction(conn):
        if not get_place(conn, place_id):
            return None, "Kho không tồn tại"
        if dest_place_id is not None and not get_place(conn, dest_place_id):
            return None, "Kho đích không tồn tại"
        rows, err = _clean_items(conn, kind, items)
        if err:
            return None, err
        moves = []
        for it in rows:
            before = stock_of(conn, it["bean_id"], place_id)
            delta = delta_for(kind, it["quantity"], before)
            after = round_qty(before + delta)
            if after < 0:
                # Nói bằng ĐƠN VỊ GỐC (tồn tính theo nó), kèm cách người dùng đã gõ
                # nếu có quy đổi — "cần 150 kg (3 bao)" dễ hiểu hơn số trần trụi.
                bu = f' {it["base_unit"]}' if it["base_unit"] else ""
                asked = f'{fmt_qty(it["quantity"])}{bu}'
                if it["unit_name"]:
                    asked += f' ({fmt_qty(it["entered_qty"])} {it["unit_name"]})'
                return None, (f'Kho không đủ "{it["bean_name"]}": còn {fmt_qty(before)}{bu}, '
                              f'cần {asked}')
            moves.append({**it, "delta": delta, "before": before})

        cur = conn.execute(
            "INSERT INTO bean_slips (kind, place_id, dest_place_id, partner, note, ymd, "
            "created_at, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, place_id, dest_place_id, str(partner or "").strip(),
             str(note or "").strip(), day, _now(), by or ""),
        )
        slip_id = cur.lastrowid
        for m in moves:
            conn.execute(
                "INSERT INTO bean_moves (slip_id, bean_id, place_id, delta, quantity, "
                "before_qty, entered_qty, unit_name, unit_factor, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (slip_id, m["bean_id"], place_id, m["delta"], m["quantity"], m["before"],
                 m["entered_qty"], m["unit_name"], m["unit_factor"], m["note"]),
            )
            if dest_place_id is not None:
                # Bút toán kép phía KHO ĐÍCH: +q, snapshot cách gõ giữ nguyên.
                conn.execute(
                    "INSERT INTO bean_moves (slip_id, bean_id, place_id, delta, quantity, "
                    "before_qty, entered_qty, unit_name, unit_factor, note) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (slip_id, m["bean_id"], dest_place_id, -m["delta"], m["quantity"],
                     stock_of(conn, m["bean_id"], dest_place_id),
                     m["entered_qty"], m["unit_name"], m["unit_factor"], m["note"]),
                )
    return get_slip(conn, slip_id), None


def _item_row(it: dict) -> dict:
    """Dòng phiếu cho người đọc: `unit` = đơn vị GỐC (mọi số quantity/delta theo nó),
    `entered_qty` + `entered_unit` = đúng thứ người dùng đã gõ. Dòng CŨ (trước khi có
    quy đổi đơn vị) không có snapshot → coi như gõ thẳng bằng đơn vị gốc."""
    factor = float(it.get("unit_factor") or 1) or 1
    entered = it.get("entered_qty")
    it["unit_factor"] = factor
    it["entered_qty"] = round_qty(entered if entered is not None else it.get("quantity") or 0)
    it["unit_name"] = it.get("unit_name") or ""
    it["entered_unit"] = it["unit_name"] or (it.get("unit") or "")
    it["converted"] = bool(it["unit_name"]) and factor != 1
    return it


def get_slip(conn, slip_id) -> dict | None:
    """Phiếu + dòng đậu (kèm tên đậu/đơn vị/tên kho để hiện thẳng).

    Phiếu CHUYỂN: items chỉ trả bút toán phía KHO NGUỒN (delta −q) — mỗi loại đậu
    1 dòng cho người đọc; phía kho đích suy ra từ `dest_place_id`/`dest_place_name`.
    """
    row = conn.execute(
        "SELECT s.*, p.name AS place_name, d.name AS dest_place_name FROM bean_slips s "
        "LEFT JOIN bean_places p ON p.id = s.place_id "
        "LEFT JOIN bean_places d ON d.id = s.dest_place_id "
        "WHERE s.id = ? AND s.deleted_at IS NULL", (slip_id,)
    ).fetchone()
    if not row:
        return None
    slip = dict(row)
    items = conn.execute(
        "SELECT m.*, b.name AS bean_name, b.unit AS unit FROM bean_moves m "
        "LEFT JOIN beans b ON b.id = m.bean_id WHERE m.slip_id = ? ORDER BY m.id", (slip_id,)
    ).fetchall()
    if slip["kind"] == "chuyen":
        items = [i for i in items if i["place_id"] == slip["place_id"]]
    slip["items"] = [_item_row(dict(i)) for i in items]
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
        # Kho khớp cả 2 đầu phiếu chuyển: trang chi tiết kho thấy hàng chuyển ĐẾN nó.
        where.append("(s.place_id = ? OR s.dest_place_id = ?)")
        args.extend([int(place_id), int(place_id)])
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
        # Soi MỌI bút toán thô (phiếu chuyển có cả dòng +q ở kho đích — items của
        # get_slip chỉ có phía nguồn, gỡ dòng đích cũng có thể làm kho đích âm).
        moves = conn.execute(
            "SELECT m.bean_id, m.place_id, m.delta, b.name AS bean_name FROM bean_moves m "
            "LEFT JOIN beans b ON b.id = m.bean_id WHERE m.slip_id = ?", (slip_id,)
        ).fetchall()
        for it in moves:
            after = round_qty(stock_of(conn, it["bean_id"], it["place_id"]) - float(it["delta"] or 0))
            if after < 0:
                return None, (f'Xoá phiếu sẽ làm "{it["bean_name"]}" âm kho — '
                              "xoá các phiếu sau nó trước")
        conn.execute("UPDATE bean_slips SET deleted_at = ?, deleted_by = ? WHERE id = ?",
                     (_now(), by or "", slip_id))
    return slip, None
