from __future__ import annotations
import json
import logging
from datetime import UTC, datetime

from .search import _invalidate_customer_patterns_cache

log = logging.getLogger("order_store.customers")


def search_customers(conn, name: str, limit: int = 20, *, sort: str = "name") -> list[dict]:
    pattern = f"%{name}%"
    order_clause = (
        "json_extract(json, '$.last_order_at') DESC NULLS LAST, firebase_key"
        if sort == "recent"
        else "firebase_key"
    )
    results = []
    for firebase_key, json_text in conn.execute(
        f"""SELECT firebase_key, json FROM customers WHERE deleted_at IS NULL
           AND (json LIKE ? OR firebase_key LIKE ?)
           ORDER BY {order_clause} LIMIT ?""",
        (pattern, pattern, limit),
    ):
        try:
            data = json.loads(json_text)
            data["_firebase_key"] = firebase_key
            results.append(data)
        except json.JSONDecodeError:
            continue
    return results


def add_customer(conn, customer_data: dict) -> tuple[bool, str]:
    name = customer_data.get("name") or customer_data.get("ten") or "unknown"
    firebase_key = name.lower().replace(" ", "_")
    now = int(datetime.now(UTC).timestamp() * 1000)  # cột updated_at = epoch ms (bigint)
    try:
        conn.execute(
            """INSERT INTO customers (firebase_key, json, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(firebase_key) DO UPDATE SET json=excluded.json, updated_at=excluded.updated_at""",
            (firebase_key, json.dumps(customer_data, ensure_ascii=False), now),
        )
        conn.commit()
        _invalidate_customer_patterns_cache()
        return True, f"✅ Đã thêm/sửa khách hàng: {name}"
    except Exception as e:
        return False, f"❌ Lỗi thêm khách hàng: {e}"


def update_customer(conn, firebase_key: str, customer_data: dict) -> tuple[bool, str]:
    now = int(datetime.now(UTC).timestamp() * 1000)  # cột updated_at = epoch ms (bigint)
    cur = conn.execute("UPDATE customers SET json = ?, updated_at = ? WHERE firebase_key = ? AND deleted_at IS NULL", (json.dumps(customer_data, ensure_ascii=False), now, firebase_key))
    conn.commit(); _invalidate_customer_patterns_cache()
    return (False, f"❌ Không tìm thấy khách hàng: {firebase_key}") if cur.rowcount == 0 else (True, f"✅ Đã cập nhật: {firebase_key}")


def get_customer_kv_id(conn, firebase_key: str) -> int | None:
    try:
        row = conn.execute("SELECT json FROM customers WHERE firebase_key = ? AND deleted_at IS NULL", (firebase_key,)).fetchone()
        return None if not row else json.loads(row["json"]).get("kh_id")
    except Exception:
        return None


def touch_customer_last_order(conn, firebase_key: str) -> None:
    """Cập nhật last_order_at cho khách hàng khi có đơn mới hoặc gán khách."""
    if not firebase_key:
        return
    try:
        row = conn.execute(
            "SELECT json FROM customers WHERE firebase_key = ? AND deleted_at IS NULL",
            (firebase_key,),
        ).fetchone()
        if not row:
            return
        data = json.loads(row["json"])
        data["last_order_at"] = datetime.now(UTC).isoformat()
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        conn.execute(
            "UPDATE customers SET json = ?, updated_at = ? WHERE firebase_key = ?",
            (json.dumps(data, ensure_ascii=False), now_ms, firebase_key),
        )
        conn.commit()
    except Exception as e:
        log.warning("touch_customer_last_order failed key=%s: %s", firebase_key, e)


def get_customer_by_key(conn, firebase_key: str) -> dict | None:
    try:
        row = conn.execute("SELECT json FROM customers WHERE firebase_key = ? AND deleted_at IS NULL", (firebase_key,)).fetchone()
        return None if not row else json.loads(row["json"])
    except Exception:
        return None
