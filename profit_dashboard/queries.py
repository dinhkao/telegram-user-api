"""Logic sync cho các endpoint JSON của dashboard lợi nhuận (chạy trong thread).

Tách từ handlers.py của repo profit-dashboard cũ: feed đơn phân trang (infinite
scroll) + freeze giá vốn vào mọi đơn. Nói chuyện với: order_store (blob orders),
product_store (calculate_order_profit / freeze_invoice_cost_prices).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

_VN_TZ = timezone(timedelta(hours=7))
# Mốc lịch sử chỉ dùng ghi chú và thao tác backfill cũ; KHÔNG giới hạn báo cáo.
MIN_THREAD_ID = 460000


def _created_vn(created):
    """(ngày YYYY-MM-DD, hiển thị dd/mm HH:MM) theo giờ VN — None nếu không đọc được."""
    try:
        if isinstance(created, str):
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        elif created > 1e10:
            dt = datetime.fromtimestamp(created / 1000, tz=timezone.utc)
        else:
            dt = datetime.fromtimestamp(created, tz=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        vn = dt.astimezone(_VN_TZ)
        return vn.strftime("%Y-%m-%d"), vn.strftime("%d/%m %H:%M")
    except Exception:
        return None, ""


def orders_feed(conn, page: int, per_page: int, since_date, until_date,
                filter_product, filter_customer, paid_only: bool = False,
                payment: str = "all", profitability: str = "all",
                cost_status: str = "all", sort: str = "newest") -> dict:
    """Cùng dữ liệu và bộ lọc với dashboard; sắp xếp trước khi phân trang."""
    from profit_dashboard.compute import scan_orders
    from profit_dashboard.filters import apply_filters, sort_orders
    from product_store.resolve import resolve_code
    if filter_product:
        filter_product = (resolve_code(conn, filter_product) or {}).get("code", filter_product)
    rows = apply_filters(scan_orders(conn, since_date, until_date),
                         filter_product, filter_customer, paid_only=paid_only,
                         payment=payment, profitability=profitability, cost_status=cost_status)
    rows = sort_orders(rows, sort)
    start = (page - 1) * per_page
    orders = [{**r, "has_cost": r["items_with_cost"] > 0,
               "cost_complete": r["cost_complete"],
               "order_text": r["text"]} for r in rows[start:start + per_page]]
    return {"orders": orders, "total": len(rows), "page": page,
            "has_more": start + per_page < len(rows)}


def freeze_all_costs(conn) -> int:
    """Đóng băng giá vốn hiện tại vào mọi đơn chưa có cost_price. Trả số đơn đã ghi."""
    from product_db import freeze_invoice_cost_prices
    from order_db import _save_order

    cur = conn.execute(
        "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL "
        "AND json IS NOT NULL AND thread_id >= ?", (MIN_THREAD_ID,))
    updated = 0
    for row in cur.fetchall():
        thread_id = row[0]
        order = json.loads(row[1])
        invoice = order.get("invoice") or []
        if not invoice or all("cost_price" in item for item in invoice):
            continue
        frozen = freeze_invoice_cost_prices(conn, invoice)
        for before, after in zip(invoice, frozen):
            if before.get("cost_price") is None and after.get("cost_price") is not None:
                after["cost_source"] = "backfill_current"
        order["invoice"] = frozen
        if _save_order(conn, thread_id, order):
            updated += 1
    return updated
