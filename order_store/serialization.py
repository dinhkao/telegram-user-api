from __future__ import annotations
import json
import logging
import time

log = logging.getLogger("order_db")


def get_order_by_thread_id(conn, thread_id: int, *, include_deleted: bool = True) -> dict | None:
    where = "WHERE thread_id = ?" if include_deleted else "WHERE thread_id = ? AND deleted_at IS NULL"
    row = conn.execute(f"SELECT json, updated_at FROM orders {where}", (thread_id,)).fetchone()
    if row is None:
        return None
    try:
        data = json.loads(row[0])
        if row[1] is not None:
            data["updated_at"] = row[1]
        return data
    except Exception:
        return None


def _get_order_firebase_key(conn, thread_id: int) -> str | None:
    row = conn.execute("SELECT firebase_key FROM orders WHERE thread_id = ? AND deleted_at IS NULL", (thread_id,)).fetchone()
    return row["firebase_key"] if row else None


def _save_order(conn, thread_id: int, data: dict) -> bool:
    try:
        conn.execute(
            "UPDATE orders SET json = ?, updated_at = ? WHERE thread_id = ? AND deleted_at IS NULL",
            (json.dumps(data, ensure_ascii=False), int(time.time() * 1000), thread_id),
        )
        return True
    except Exception as e:
        log.error("Failed to save order thread=%d: %s", thread_id, e)
        return False


def _update_order_json_field(conn, thread_id: int, field_path: str, value) -> bool:
    try:
        # JSON-encode EVERY value, not just dict/list. A bare string previously
        # became json('Anh Tú') — malformed JSON — so string writes (e.g.
        # $.customer_name, string customer IDs) silently failed. json.dumps makes
        # it json('"Anh Tú"'), which parses correctly.
        sql_val = json.dumps(value, ensure_ascii=False)
        conn.execute(
            "UPDATE orders SET json = json_set(json, ?, json(?)), updated_at = ? WHERE thread_id = ? AND deleted_at IS NULL",
            (field_path, sql_val, int(time.time() * 1000), thread_id),
        )
        return True
    except Exception as e:
        log.error("Failed to update %s for thread=%d: %s", field_path, thread_id, e)
        return False


def _create_order(conn, firebase_key: str, thread_id: int, channel_id: int, message_id: int, data: dict) -> bool:
    try:
        conn.execute(
            "INSERT OR IGNORE INTO orders(firebase_key, thread_id, channel_id, message_id, json, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (firebase_key, thread_id, channel_id, message_id, json.dumps(data, ensure_ascii=False), int(time.time() * 1000)),
        )
        return True
    except Exception as e:
        log.error("Failed to create order thread=%d: %s", thread_id, e)
        return False


def get_order_json(conn, thread_id: int) -> dict | None:
    row = conn.execute("SELECT json FROM orders WHERE thread_id = ? AND deleted_at IS NULL", (thread_id,)).fetchone()
    if not row or not row["json"]:
        return None
    return json.loads(row["json"])
