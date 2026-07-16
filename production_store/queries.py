from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta

_VN_TZ = timezone(timedelta(hours=7))

_COLUMNS = (
    "thread_id",
    "channel_id",
    "message_id",
    "date",
    "date_code",
    "sp_name",
    "sp_mam",
    "sp_luong",
    "sx_target",
    "total",
    "numbers",
    "bang",
    "ghi_chu",
    "kind",
    "updated_at",
    "product_id",
    "lock_override",
    "luong_1sp",
)
_JSON_COLUMNS = {"numbers", "bang"}


def get_slip(conn, thread_id) -> dict | None:
    row = conn.execute(
        "SELECT s.*, COALESCE(pr.code, s.sp_name) AS sp_name_live "
        "FROM production_slips s LEFT JOIN products pr ON pr.id = s.product_id "
        "WHERE s.thread_id = ?", (thread_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    data["sp_name"] = data.pop("sp_name_live") or data.get("sp_name")
    try:
        data["numbers"] = json.loads(data["numbers"]) if data.get("numbers") else []
    except (TypeError, ValueError):
        data["numbers"] = []
    try:
        data["bang"] = json.loads(data["bang"]) if data.get("bang") else None
    except (TypeError, ValueError):
        data["bang"] = None
    return data


def _kind_clause(kind):
    """(where_sql, params) lọc theo loại phiếu; kind None/'' = mọi phiếu.
    Coi kind rỗng/NULL trong DB là 'san_xuat' (mặc định cũ)."""
    if kind == "dong_goi":
        return " WHERE kind = 'dong_goi'", ()
    if kind == "san_xuat":
        return " WHERE (kind IS NULL OR kind = '' OR kind = 'san_xuat')", ()
    return "", ()


def list_slips(conn, limit: int = 20, offset: int = 0, kind: str | None = None, day: str | None = None) -> list[dict]:
    """Slips theo NGÀY TẠO mới→cũ (date_code lúc tạo), phân trang. Row nhẹ. Lọc theo
    kind + day (day='YYYYMMDD' → khớp date_code LIKE 'YYYYMMDD%' = phiếu 1 ngày)."""
    where, wp = _kind_clause(kind)
    if where:
        where = where.replace("kind", "s.kind")
    if day:
        where = (where + " AND " if where else " WHERE ") + "s.date_code LIKE ?"
        wp = (*wp, day + "%")
    rows = conn.execute(
        "SELECT s.thread_id, s.date, s.date_code, s.product_id, "
        "COALESCE(pr.code, s.sp_name) AS sp_name, s.sp_mam, s.sx_target, s.total, "
        "s.ghi_chu, s.kind, s.updated_at FROM production_slips s "
        "LEFT JOIN products pr ON pr.id = s.product_id" + where +
        " ORDER BY s.date_code DESC, s.thread_id DESC LIMIT ? OFFSET ?",
        (*wp, limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]


def count_slips(conn, kind: str | None = None, day: str | None = None) -> int:
    where, wp = _kind_clause(kind)
    if day:
        where = (where + " AND " if where else " WHERE ") + "date_code LIKE ?"
        wp = (*wp, day + "%")
    return int(conn.execute("SELECT COUNT(*) FROM production_slips" + where, wp).fetchone()[0])


def upsert_slip(conn, thread_id, **fields) -> bool:
    conn.execute("INSERT OR IGNORE INTO production_slips (thread_id) VALUES (?)", (thread_id,))
    updates, params = [], []
    for key, value in fields.items():
        if key not in _COLUMNS or key == "thread_id":
            continue
        if key in _JSON_COLUMNS:
            value = json.dumps(value, ensure_ascii=False)
        updates.append(f"{key} = ?")
        params.append(value)
    updates.append("updated_at = datetime('now')")
    params.append(thread_id)
    conn.execute(f"UPDATE production_slips SET {', '.join(updates)} WHERE thread_id = ?", params)
    conn.commit()
    return True


def set_sp(conn, thread_id, name, mam, luong) -> bool:
    """Gán SP cho phiếu: ghi CẢ product_id (danh tính) + sp_name (snapshot mã hiện
    hành — gõ mã cũ tự chuẩn hoá). Tên không phải mã SP → product_id NULL.
    LƯƠNG 1 SP CỐ ĐỊNH THEO PHIẾU: gán/đổi SP → chốt luong_1sp từ bảng lương hiện
    tại; gán lại ĐÚNG SP cũ → giữ đơn giá đã chốt (văn phòng có thể đã sửa tay)."""
    from product_store import resolve_code
    from production_store.wages import wage_for_code
    prod = resolve_code(conn, name)
    new_code = prod["code"] if prod else str(name or "").strip().upper()
    cur = conn.execute(
        "SELECT sp_name, luong_1sp FROM production_slips WHERE thread_id = ?", (thread_id,)
    ).fetchone()
    same_sp = cur is not None and str(cur["sp_name"] or "").strip().upper() == new_code
    # Phiếu ĐÃ có báo cáo thợ → tiền công đã tính theo luong_1sp đã chốt; đổi SP lúc
    # này KHÔNG được lặng lẽ re-price (sẽ đổi số tiền của các dòng đã tính). Giữ
    # nguyên luong_1sp cũ, chỉ đổi SP.
    try:
        has_report = conn.execute(
            "SELECT 1 FROM production_report_rows WHERE thread_id = ? LIMIT 1", (thread_id,)
        ).fetchone() is not None
    except Exception:
        has_report = False   # bảng chưa tồn tại → coi như chưa có báo cáo

    extra = {}
    if not (same_sp and cur["luong_1sp"] is not None) and not has_report:
        w = wage_for_code(conn, new_code)
        extra["luong_1sp"] = w if w > 0 else None   # NULL = chưa chốt → theo bảng lương
    if prod:
        return upsert_slip(conn, thread_id, sp_name=prod["code"], sp_mam=mam, sp_luong=luong,
                           product_id=prod["id"], **extra)
    return upsert_slip(conn, thread_id, sp_name=name, sp_mam=mam, sp_luong=luong, product_id=None, **extra)


def set_slip_wage(conn, thread_id, luong) -> bool:
    """Văn phòng chốt/sửa đơn giá lương / 1 SP của RIÊNG phiếu này (snapshot).
    luong None → về NULL (theo bảng lương hiện tại); 0 = phiếu không tính tiền."""
    val = None if luong is None else max(0.0, float(luong))
    return upsert_slip(conn, thread_id, luong_1sp=val)


def set_target(conn, thread_id, sx_target) -> bool:
    return upsert_slip(conn, thread_id, sx_target=sx_target)


def set_kind(conn, thread_id, kind) -> bool:
    """Loại phiếu: 'san_xuat' (có bảng báo cáo thợ) | 'dong_goi' (không có)."""
    k = "dong_goi" if str(kind) == "dong_goi" else "san_xuat"
    return upsert_slip(conn, thread_id, kind=k)


def set_note(conn, thread_id, ghi_chu) -> bool:
    return upsert_slip(conn, thread_id, ghi_chu=ghi_chu)


def set_lock_override(conn, thread_id, value) -> bool:
    """Admin ghi đè khoá phiếu: 'locked' | 'unlocked' | None (về tự-động 24h)."""
    v = value if value in ("locked", "unlocked") else None
    return upsert_slip(conn, thread_id, lock_override=v)


def add_number(conn, thread_id, amount, note, by=None, at=None) -> float:
    """Thêm 1 lần nhập số lượng nhận. Lưu kèm thời điểm (at) + người nhập (by)."""
    slip = get_slip(conn, thread_id) or {}
    numbers = slip.get("numbers") or []
    numbers.append({
        "amount": amount,
        "note": note or "",
        "at": at or datetime.now(_VN_TZ).isoformat(timespec="seconds"),
        "by": by or "",
    })
    total = sum(item.get("amount", 0) for item in numbers)
    upsert_slip(conn, thread_id, numbers=numbers, total=total)
    return total


def set_total(conn, thread_id, total) -> bool:
    return upsert_slip(conn, thread_id, total=total)


def remove_number_by_note(conn, thread_id, note) -> float:
    """Gỡ 1 entry numbers theo note (vd '📦 K2L-004' khi xoá thùng) → total tính lại
    từ danh sách còn lại (numbers là nguồn thật, set_total bị add_number ghi đè)."""
    slip = get_slip(conn, thread_id)
    if not slip:
        return 0.0
    numbers = slip.get("numbers") or []
    for i, it in enumerate(numbers):
        if (it.get("note") or "") == note:
            numbers.pop(i)
            break
    total = sum(item.get("amount", 0) for item in numbers)
    upsert_slip(conn, thread_id, numbers=numbers, total=total)
    return total


def set_bang(conn, thread_id, bang) -> bool:
    ok = upsert_slip(conn, thread_id, bang=bang)
    # Ghi thêm vào bảng QUAN HỆ production_report_rows (cho dashboard). Phụ — không chặn.
    try:
        from production_store.report_rows import replace_report_rows
        replace_report_rows(conn, thread_id, bang)
    except Exception:
        pass
    # PHỤ CẤP TỰ ĐỘNG theo ghi chú (Kim vít → cao nhất, nghỉ → xoá…). Phụ — không chặn lưu.
    try:
        from production_store.allowance_auto import apply_auto_allowances
        apply_auto_allowances(conn, thread_id, bang)
    except Exception:
        pass
    return ok


def delete_slip(conn, thread_id) -> bool:
    conn.execute("DELETE FROM production_slips WHERE thread_id = ?", (thread_id,))
    conn.commit()
    return True
