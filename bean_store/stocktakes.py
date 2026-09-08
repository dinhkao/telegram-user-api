"""PHIẾU KIỂM KHO ĐẬU (`bean_stocktakes` + `bean_stocktake_items`, app.db).

Luồng: tạo phiếu cho 1 kho → CHỤP sổ sách (expected = tồn từng loại đậu lúc đó, đủ
MỌI loại trong danh mục để phát hiện hàng chưa vào sổ) → người đếm ghi số (kép
[N đơn vị quy đổi] + [M gốc], quy về gốc) → CHỐT: sinh 1 phiếu điều chỉnh với
delta = đếm − sổ LÚC CHỤP (bean_store.slips.create_adjustment_from_counts) → status
'done'. Kho biến động sau khi chụp → get_stocktake gắn cờ `stale` từng dòng; Đồng bộ
sổ (resync) đặt lại expected theo tồn hiện tại, GIỮ số đã đếm. Mỗi kho 1 nháp.
Luật thuần ở bean_store.domain (count_to_base, stocktake_summary). Dùng bởi
server_app/bean_stocktake_routes.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

from utils.db import transaction

from .catalog import get_place, list_beans
from .domain import (STOCKTAKE_STATUSES, count_to_base, parse_qty, round_qty,
                     stocktake_summary)
from .slips import create_adjustment_from_counts, get_slip
from .stock import stock_of
from .units import resolve_unit, units_by_bean


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(conn, sid) -> dict | None:
    r = conn.execute(
        "SELECT t.*, p.name AS place_name FROM bean_stocktakes t "
        "LEFT JOIN bean_places p ON p.id = t.place_id WHERE t.id = ?", (sid,)
    ).fetchone()
    return dict(r) if r else None


def create_stocktake(conn, place_id, *, note: str = "", by: str | None = None
                     ) -> tuple[dict | None, str | None]:
    """Mở phiếu kiểm cho 1 kho — chụp tồn MỌI loại đậu trong danh mục. 1 nháp/kho."""
    try:
        place_id = int(place_id)
    except (TypeError, ValueError):
        return None, "Cần chọn kho"
    with transaction(conn):
        if not get_place(conn, place_id):
            return None, "Kho không tồn tại"
        dup = conn.execute(
            "SELECT id FROM bean_stocktakes WHERE place_id = ? AND status = 'draft'", (place_id,)
        ).fetchone()
        if dup:
            return None, f"Kho này đang có phiếu kiểm #{dup['id']} chưa chốt — mở phiếu đó"
        beans = list_beans(conn)
        if not beans:
            return None, "Chưa có loại đậu nào trong danh mục"
        cur = conn.execute(
            "INSERT INTO bean_stocktakes (place_id, status, note, created_at, created_by) "
            "VALUES (?, 'draft', ?, ?, ?)", (place_id, str(note or "").strip(), _now(), by or ""))
        sid = cur.lastrowid
        for b in beans:
            conn.execute(
                "INSERT INTO bean_stocktake_items (stocktake_id, bean_id, expected_qty) "
                "VALUES (?, ?, ?)", (sid, b["id"], stock_of(conn, b["id"], place_id)))
    return get_stocktake(conn, sid), None


def get_stocktake(conn, sid) -> dict | None:
    """Phiếu + dòng (tên đậu, đơn vị gốc, đơn vị quy đổi để gõ kép, diff, cờ stale).

    Nháp: `live_qty` = tồn hiện tại; `stale` = sổ đã đổi so với lúc chụp (kho biến
    động sau khi bắt đầu kiểm). Phiếu done/voided: live không còn ý nghĩa → không gắn.
    """
    st = _row(conn, sid)
    if not st:
        return None
    rows = conn.execute(
        "SELECT i.*, b.name AS bean_name, b.unit AS unit, b.deleted_at AS bean_deleted "
        "FROM bean_stocktake_items i LEFT JOIN beans b ON b.id = i.bean_id "
        "WHERE i.stocktake_id = ? ORDER BY b.name COLLATE NOCASE, i.id", (sid,)
    ).fetchall()
    units = units_by_bean(conn) if st["status"] == "draft" else {}
    items = []
    stale = 0
    for r in rows:
        it = dict(r)
        it["bean_name"] = it.get("bean_name") or f"Đậu #{it['bean_id']}"
        it["unit"] = it.get("unit") or ""
        it["expected_qty"] = round_qty(it.get("expected_qty") or 0)
        c = it.get("counted_qty")
        it["counted_qty"] = None if c is None else round_qty(c)
        it["diff"] = None if c is None else round_qty(it["counted_qty"] - it["expected_qty"])
        if st["status"] == "draft":
            it["units"] = units.get(int(it["bean_id"]), [])
            it["live_qty"] = stock_of(conn, it["bean_id"], st["place_id"])
            it["stale"] = it["live_qty"] != it["expected_qty"]
            stale += int(it["stale"])
        items.append(it)
    st["items"] = items
    st["summary"] = stocktake_summary(items)
    st["stale_count"] = stale
    if st.get("slip_id"):
        slip = get_slip(conn, st["slip_id"])
        st["slip"] = ({"id": slip["id"], "ymd": slip["ymd"], "total_quantity": slip["total_quantity"],
                       "lines": len(slip["items"])} if slip else None)   # None = admin đã xoá phiếu
    return st


def list_stocktakes(conn, *, place_id=None, status: str | None = None,
                    limit: int = 30, offset: int = 0) -> tuple[list[dict], int]:
    """Phiếu kiểm mới → cũ, kèm tóm tắt (không kèm dòng). Trả (danh sách, tổng)."""
    where, args = ["1=1"], []
    if place_id:
        where.append("t.place_id = ?")
        args.append(int(place_id))
    if status:
        if status not in STOCKTAKE_STATUSES:
            return [], 0
        where.append("t.status = ?")
        args.append(status)
    cond = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) c FROM bean_stocktakes t WHERE {cond}", args).fetchone()["c"]
    rows = conn.execute(
        f"SELECT t.*, p.name AS place_name FROM bean_stocktakes t "
        f"LEFT JOIN bean_places p ON p.id = t.place_id WHERE {cond} "
        "ORDER BY (t.status = 'draft') DESC, t.id DESC LIMIT ? OFFSET ?",
        [*args, int(limit), int(offset)]).fetchall()
    out = []
    for r in rows:
        st = dict(r)
        items = conn.execute(
            "SELECT expected_qty, counted_qty FROM bean_stocktake_items WHERE stocktake_id = ?",
            (st["id"],)).fetchall()
        st["summary"] = stocktake_summary([dict(i) for i in items])
        out.append(st)
    return out, int(total)


def _draft(conn, sid) -> tuple[dict | None, str | None]:
    st = _row(conn, sid)
    if not st:
        return None, "Không tìm thấy phiếu kiểm"
    if st["status"] != "draft":
        return None, "Phiếu kiểm đã chốt/huỷ, không sửa được"
    return st, None


def set_counts(conn, sid, items, *, by: str | None = None) -> tuple[dict | None, str | None]:
    """Ghi số đếm cho 1 hay nhiều dòng (upsert theo bean_id, phiếu phải là nháp).

    items = [{bean_id, bulk?, loose?, unit_id?, note?}] — bulk theo đơn vị quy đổi
    `unit_id` (None = không dùng), loose theo đơn vị GỐC; cả 2 trống = XOÁ số đếm
    (về chưa đếm). Số âm bị từ chối.
    """
    if not isinstance(items, (list, tuple)) or not items:
        return None, "Không có dòng nào để ghi"
    with transaction(conn):
        st, err = _draft(conn, sid)
        if err:
            return None, err
        for raw in items:
            if not isinstance(raw, dict):
                return None, "Dòng không hợp lệ"
            try:
                bean_id = int(raw.get("bean_id"))
            except (TypeError, ValueError):
                return None, "Thiếu loại đậu ở một dòng"
            have = conn.execute(
                "SELECT id FROM bean_stocktake_items WHERE stocktake_id = ? AND bean_id = ?",
                (sid, bean_id)).fetchone()
            if not have:
                return None, f"Loại đậu #{bean_id} không có trong phiếu kiểm này (bấm Đồng bộ sổ)"
            bulk = parse_qty(raw.get("bulk")) if str(raw.get("bulk") or "").strip() != "" else None
            loose = parse_qty(raw.get("loose")) if str(raw.get("loose") or "").strip() != "" else None
            if (raw.get("bulk") not in (None, "") and bulk is None) or \
               (raw.get("loose") not in (None, "") and loose is None):
                return None, "Số đếm không hợp lệ"
            if (bulk or 0) < 0 or (loose or 0) < 0:
                return None, "Số đếm không được âm"
            unit_name, factor, uerr = resolve_unit(conn, bean_id, raw.get("unit_id"))
            if uerr:
                return None, uerr
            if bulk is not None and not unit_name:
                # Gõ số "kiện" mà không chọn đơn vị → cộng thẳng vào phần lẻ (factor 1).
                loose = round_qty((loose or 0) + bulk)
                bulk = None
            counted = count_to_base(bulk, loose, factor)
            conn.execute(
                "UPDATE bean_stocktake_items SET counted_qty = ?, counted_bulk = ?, "
                "counted_loose = ?, unit_id = ?, unit_name = ?, unit_factor = ?, note = ?, "
                "counted_at = ?, counted_by = ? WHERE id = ?",
                (counted, bulk, loose,
                 int(raw["unit_id"]) if unit_name and raw.get("unit_id") else None,
                 unit_name, factor, str(raw.get("note") or "").strip(),
                 _now() if counted is not None else None, (by or "") if counted is not None else "",
                 have["id"]))
        conn.execute("UPDATE bean_stocktakes SET updated_at = ?, updated_by = ? WHERE id = ?",
                     (_now(), by or "", sid))
    return get_stocktake(conn, sid), None


def resync_stocktake(conn, sid, *, by: str | None = None) -> tuple[dict | None, str | None]:
    """Đặt lại sổ (expected) theo tồn HIỆN TẠI + thêm dòng cho loại đậu mới trong danh
    mục. GIỮ NGUYÊN số đã đếm. Dùng khi kho biến động sau lúc bắt đầu kiểm."""
    with transaction(conn):
        st, err = _draft(conn, sid)
        if err:
            return None, err
        have = {int(r["bean_id"]) for r in conn.execute(
            "SELECT bean_id FROM bean_stocktake_items WHERE stocktake_id = ?", (sid,)).fetchall()}
        for b in list_beans(conn):
            live = stock_of(conn, b["id"], st["place_id"])
            if int(b["id"]) in have:
                conn.execute("UPDATE bean_stocktake_items SET expected_qty = ? "
                             "WHERE stocktake_id = ? AND bean_id = ?", (live, sid, b["id"]))
            else:
                conn.execute("INSERT INTO bean_stocktake_items (stocktake_id, bean_id, expected_qty) "
                             "VALUES (?, ?, ?)", (sid, b["id"], live))
        conn.execute("UPDATE bean_stocktakes SET updated_at = ?, updated_by = ? WHERE id = ?",
                     (_now(), by or "", sid))
    return get_stocktake(conn, sid), None


def complete_stocktake(conn, sid, *, by: str | None = None, note: str = ""
                       ) -> tuple[dict | None, str | None]:
    """CHỐT: dòng đã đếm và lệch sổ → 1 phiếu điều chỉnh (delta = đếm − sổ lúc chụp);
    dòng chưa đếm BỎ QUA; mọi dòng khớp → chốt không sinh phiếu. All-or-nothing."""
    with transaction(conn):
        st, err = _draft(conn, sid)
        if err:
            return None, err
        rows = conn.execute(
            "SELECT bean_id, expected_qty, counted_qty FROM bean_stocktake_items "
            "WHERE stocktake_id = ? AND counted_qty IS NOT NULL", (sid,)).fetchall()
        if not rows:
            return None, "Chưa đếm dòng nào — ghi số đếm trước khi chốt"
        lines = [{"bean_id": r["bean_id"], "counted": r["counted_qty"], "expected": r["expected_qty"]}
                 for r in rows if round_qty(r["counted_qty"]) != round_qty(r["expected_qty"] or 0)]
        slip_id = None
        if lines:
            text = str(note or "").strip() or f"Kiểm kho #{sid}"
            slip, err = create_adjustment_from_counts(conn, st["place_id"], lines,
                                                      stocktake_id=sid, note=text, by=by)
            if err:
                return None, err
            slip_id = slip["id"]
        conn.execute(
            "UPDATE bean_stocktakes SET status = 'done', completed_at = ?, completed_by = ?, "
            "slip_id = ?, note = CASE WHEN ? != '' THEN ? ELSE note END WHERE id = ?",
            (_now(), by or "", slip_id, str(note or "").strip(), str(note or "").strip(), sid))
    return get_stocktake(conn, sid), None


def void_stocktake(conn, sid, *, by: str | None = None) -> tuple[dict | None, str | None]:
    """Huỷ nháp — không đụng tồn, giải phóng kho để mở phiếu kiểm mới."""
    with transaction(conn):
        st, err = _draft(conn, sid)
        if err:
            return None, err
        conn.execute("UPDATE bean_stocktakes SET status = 'voided', voided_at = ?, voided_by = ? "
                     "WHERE id = ?", (_now(), by or "", sid))
    return get_stocktake(conn, sid), None
