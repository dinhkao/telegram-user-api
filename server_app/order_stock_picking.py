"""Icon ⏺ "đang xuất kho" cho card dashboard đơn — đọc box_allocations (app.db).

Đơn chưa soạn (icon ❌) + chưa chốt xuất kho nhưng ĐÃ chọn ≥1 thùng cho đơn →
đổi icon bước Soạn thành ⏺. Chỉ áp cho row danh sách webapp (server_app/orders_api),
KHÔNG đổi status_icons của main message Telegram.
"""
from __future__ import annotations

PICKING_ICON = "⏺"


def apply_picking_icon(icons: str, picking: bool) -> str:
    """Thay icon bước Soạn (vị trí 1) ❌ → ⏺ khi đơn đang xuất kho dở. Thuần."""
    chars = list(icons or "")
    if picking and len(chars) > 1 and chars[1] == "❌":
        chars[1] = PICKING_ICON
    return "".join(chars)


def attach_stock_picking(conn, orders: list[dict]) -> None:
    """1 truy vấn gộp: đơn nào có phần thùng xuất (kind='order') → áp icon ⏺.
    Đơn đã chốt kho có icon 📦 và đơn đã soạn có ✅ nên apply_picking_icon tự bỏ qua."""
    ids = [o["thread_id"] for o in orders
           if o.get("thread_id") is not None and len(o.get("task_icons") or "") > 1
           and list(o["task_icons"])[1] == "❌"]
    if not ids:
        return
    try:
        ph = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT DISTINCT order_thread_id FROM box_allocations "
            f"WHERE order_thread_id IN ({ph}) AND COALESCE(kind,'order') = 'order'",
            ids,
        ).fetchall()
    except Exception:
        return   # bảng chưa tồn tại (chưa ai dùng kho) → giữ nguyên icon
    picking = {r[0] for r in rows}
    for o in orders:
        if o.get("thread_id") in picking:
            o["task_icons"] = apply_picking_icon(o.get("task_icons") or "", True)
