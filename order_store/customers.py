from __future__ import annotations
import json
from datetime import UTC, datetime

from .search import _invalidate_customer_patterns_cache


def search_customers(conn, name: str, limit: int = 20) -> list[dict]:
    pattern = f"%{name}%"
    results = []
    for firebase_key, json_text in conn.execute(
        """SELECT firebase_key, json FROM customers WHERE deleted_at IS NULL
           AND (json LIKE ? OR firebase_key LIKE ?)
           ORDER BY firebase_key LIMIT ?""",
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


def get_customer_by_key(conn, firebase_key: str) -> dict | None:
    try:
        row = conn.execute("SELECT json FROM customers WHERE firebase_key = ? AND deleted_at IS NULL", (firebase_key,)).fetchone()
        return None if not row else json.loads(row["json"])
    except Exception:
        return None
