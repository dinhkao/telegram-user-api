from __future__ import annotations
import json
from datetime import UTC, datetime


def delete_all_tasks(conn) -> tuple[int, str]:
    count, now = 0, datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    for row in conn.execute("SELECT thread_id, json FROM orders WHERE deleted_at IS NULL"):
        if not row["json"]:
            continue
        order = json.loads(row["json"])
        if "task_status" in order:
            del order["task_status"]
            conn.execute("UPDATE orders SET json = ?, updated_at = ? WHERE thread_id = ?", (json.dumps(order, ensure_ascii=False), now, row["thread_id"]))
            count += 1
    conn.commit()
    return count, f"✅ Đã xóa task của {count} đơn hàng"


def migrate_tasks_to_v2(conn) -> tuple[int, str]:
    count, now = 0, datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    for row in conn.execute("SELECT thread_id, json FROM orders WHERE deleted_at IS NULL"):
        if not row["json"]:
            continue
        order = json.loads(row["json"])
        if order.get("flow_version") != 2:
            order["flow_version"] = 2
            order["done_after_20250124"] = True
            conn.execute("UPDATE orders SET json = ?, updated_at = ? WHERE thread_id = ?", (json.dumps(order, ensure_ascii=False), now, row["thread_id"]))
            count += 1
    conn.commit()
    return count, f"✅ Đã migrate {count} đơn sang V2"
