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
        before = get_order_by_thread_id(conn, thread_id)
        try:   # đóng dấu nguồn đơn giá từng dòng (đơn trước / bảng giá / ai nhập)
            from .price_origin import stamp_price_origin
            stamp_price_origin(conn, thread_id, before, data)
        except Exception as e:  # noqa: BLE001 — best-effort, không chặn lưu đơn
            log.warning("price origin stamp failed thread=%d: %s", thread_id, e)
        conn.execute(
            "UPDATE orders SET json = ?, updated_at = ? WHERE thread_id = ? AND deleted_at IS NULL",
            (json.dumps(data, ensure_ascii=False), int(time.time() * 1000), thread_id),
        )
        kh = data.get("khach_hang_id") or data.get("khID")
        if kh:  # hoá đơn có thể vừa đổi → bỏ cache "giá mua lần gần nhất" của khách
            from .last_prices import invalidate_last_price_cache
            invalidate_last_price_cache(kh)
        from .mutation_audit import record_order_change
        record_order_change(conn, thread_id, before, data)
        return True
    except Exception as e:
        log.error("Failed to save order thread=%d: %s", thread_id, e)
        return False


def _update_order_json_field(conn, thread_id: int, field_path: str, value) -> bool:
    try:
        before = get_order_by_thread_id(conn, thread_id)
        if field_path == "$.invoice" and isinstance(value, list):
            # Ghi hoá đơn kiểu 1 trường (auto-parse đơn MỚI — channel_handlers/parse) cũng
            # phải đóng dấu nguồn đơn giá như _save_order — trước đây lọt: đơn mới không có
            # ghi chú "= đơn trước / bảng giá / ai nhập" cho tới lần sửa hoá đơn đầu tiên.
            try:
                from .price_origin import stamp_price_origin
                preview = dict(before or {})
                preview["invoice"] = [dict(it) if isinstance(it, dict) else it for it in value]
                stamp_price_origin(conn, thread_id, before, preview)
                value = preview["invoice"]
            except Exception as e:  # noqa: BLE001 — best-effort, không chặn ghi hoá đơn
                log.warning("price origin stamp (field) failed thread=%d: %s", thread_id, e)
        # JSON-encode EVERY value, not just dict/list. A bare string previously
        # became json('Anh Tú') — malformed JSON — so string writes (e.g.
        # $.customer_name, string customer IDs) silently failed. json.dumps makes
        # it json('"Anh Tú"'), which parses correctly.
        sql_val = json.dumps(value, ensure_ascii=False)
        conn.execute(
            "UPDATE orders SET json = json_set(json, ?, json(?)), updated_at = ? WHERE thread_id = ? AND deleted_at IS NULL",
            (field_path, sql_val, int(time.time() * 1000), thread_id),
        )
        after = get_order_by_thread_id(conn, thread_id)
        from .mutation_audit import record_order_change
        record_order_change(conn, thread_id, before, after)
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
