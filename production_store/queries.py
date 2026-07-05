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
    "updated_at",
)
_JSON_COLUMNS = {"numbers", "bang"}


def get_slip(conn, thread_id) -> dict | None:
    row = conn.execute("SELECT * FROM production_slips WHERE thread_id = ?", (thread_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    try:
        data["numbers"] = json.loads(data["numbers"]) if data.get("numbers") else []
    except (TypeError, ValueError):
        data["numbers"] = []
    try:
        data["bang"] = json.loads(data["bang"]) if data.get("bang") else None
    except (TypeError, ValueError):
        data["bang"] = None
    return data


def list_slips(conn, limit: int = 20, offset: int = 0) -> list[dict]:
    """Slips theo NGÀY TẠO mới→cũ (date_code lúc tạo), phân trang. Row nhẹ."""
    rows = conn.execute(
        "SELECT thread_id, date, date_code, sp_name, sp_mam, sx_target, total, "
        "ghi_chu, updated_at FROM production_slips "
        "ORDER BY date_code DESC, thread_id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]


def count_slips(conn) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM production_slips").fetchone()[0])


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
    return upsert_slip(conn, thread_id, sp_name=name, sp_mam=mam, sp_luong=luong)


def set_target(conn, thread_id, sx_target) -> bool:
    return upsert_slip(conn, thread_id, sx_target=sx_target)


def set_note(conn, thread_id, ghi_chu) -> bool:
    return upsert_slip(conn, thread_id, ghi_chu=ghi_chu)


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


def set_bang(conn, thread_id, bang) -> bool:
    ok = upsert_slip(conn, thread_id, bang=bang)
    # Ghi thêm vào bảng QUAN HỆ production_report_rows (cho dashboard). Phụ — không chặn.
    try:
        from production_store.report_rows import replace_report_rows
        replace_report_rows(conn, thread_id, bang)
    except Exception:
        pass
    return ok


def delete_slip(conn, thread_id) -> bool:
    conn.execute("DELETE FROM production_slips WHERE thread_id = ?", (thread_id,))
    conn.commit()
    return True
