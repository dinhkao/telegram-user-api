from __future__ import annotations
import http.client
import json
import os
from datetime import UTC, datetime

from .schema import transaction
from .serialization import _save_order, get_order_by_thread_id

FINAL_TELEGRAM_URL = os.getenv("FINAL_TELEGRAM_URL", "http://localhost:3000")


def delete_order(conn, thread_id: int, force: bool = False) -> tuple[bool, str]:
    row = conn.execute("SELECT firebase_key, json FROM orders WHERE thread_id = ? AND deleted_at IS NULL", (thread_id,)).fetchone()
    if not row:
        return False, "Không tìm thấy đơn hàng"
    firebase_key, order = row["firebase_key"], json.loads(row["json"] or "{}")
    if not force and order.get("trang_thai") == "Done":
        return False, "Đơn hàng đã hoàn thành, dùng `del hd` để xóa cưỡng chế"
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    order["del"], order["deleted_at"] = True, now
    conn.execute("UPDATE orders SET json = ?, deleted_at = ? WHERE thread_id = ?", (json.dumps(order, ensure_ascii=False), now, thread_id))
    conn.commit()
    return True, f"🗑️ Đã xóa đơn hàng (key={firebase_key})"


def _call_final_telegram(endpoint: str, body: dict, timeout: int = 10) -> dict | None:
    host_port = FINAL_TELEGRAM_URL.replace("http://", "").replace("https://", "")
    host, _, port_str = host_port.partition(":")
    try:
        conn_http = http.client.HTTPConnection(host, int(port_str) if port_str else 80, timeout=timeout)
        conn_http.request("POST", endpoint, json.dumps(body, ensure_ascii=False).encode(), {"Content-Type": "application/json"})
        resp = conn_http.getresponse()
        data = json.loads(resp.read())
        conn_http.close()
        return data
    except Exception as e:
        from .serialization import log
        log.error("_call_final_telegram %s: %s", endpoint, e)
        return None


def get_order_html(conn, thread_id: int) -> str:
    result = _call_final_telegram("/api/order/get-html", {"thread_id": thread_id})
    return "❌ Không thể lấy HTML" if not result else (result.get("html", "") or "Không có HTML")


def set_order_flag(conn, thread_id: int, flag_name: str, value: bool | str) -> tuple[bool, str]:
    with transaction(conn):   # atomic read-modify-write (see order_store.schema.transaction)
        data = get_order_by_thread_id(conn, thread_id)
        if data is None:
            return False, "Không tìm thấy đơn hàng"
        data[flag_name] = value
        data["updated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        return (True, f"✅ Đã cập nhật {flag_name}") if _save_order(conn, thread_id, data) else (False, "❌ Lỗi lưu đơn hàng")


def save_order_invoice(conn, thread_id: int, invoice: list[dict]) -> tuple[bool, str]:
    with transaction(conn):   # atomic read-modify-write
        data = get_order_by_thread_id(conn, thread_id)
        if data is None:
            return False, "Không tìm thấy đơn hàng"
        data["invoice"], data["updated_at"] = invoice, datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        return (True, f"✅ Đã lưu {len(invoice)} sản phẩm") if _save_order(conn, thread_id, data) else (False, "❌ Lỗi lưu đơn hàng")
