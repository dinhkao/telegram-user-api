from __future__ import annotations
import json

_COLUMNS = ("thread_id", "name", "price_list", "updated_at")
_JSON_COLUMNS = {"price_list"}


def get_slip(conn, thread_id) -> dict | None:
    row = conn.execute("SELECT * FROM bang_gia_slips WHERE thread_id = ?", (thread_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    try:
        data["price_list"] = json.loads(data["price_list"]) if data.get("price_list") else {}
    except (TypeError, ValueError):
        data["price_list"] = {}
    return data


def upsert_slip(conn, thread_id, **fields) -> bool:
    conn.execute("INSERT OR IGNORE INTO bang_gia_slips (thread_id) VALUES (?)", (thread_id,))
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
    conn.execute(f"UPDATE bang_gia_slips SET {', '.join(updates)} WHERE thread_id = ?", params)
    conn.commit()
    return True


def set_name(conn, thread_id, name) -> bool:
    return upsert_slip(conn, thread_id, name=name)


def set_price(conn, thread_id, sp, price) -> dict:
    slip = get_slip(conn, thread_id) or {}
    price_list = slip.get("price_list") or {}
    price_list[sp] = price
    upsert_slip(conn, thread_id, price_list=price_list)
    return price_list


def get_price_list(conn, thread_id) -> dict:
    slip = get_slip(conn, thread_id)
    return (slip or {}).get("price_list") or {}
