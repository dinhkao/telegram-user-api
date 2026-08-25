"""Logic sync cho các endpoint JSON của dashboard lợi nhuận (chạy trong thread).

Tách từ handlers.py của repo profit-dashboard cũ: feed đơn phân trang (infinite
scroll) + freeze giá vốn vào mọi đơn. Nói chuyện với: order_store (blob orders),
product_store (calculate_order_profit / freeze_invoice_cost_prices).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from product_db import calculate_order_profit

from profit_dashboard.utils import resolve_customer_name

_VN_TZ = timezone(timedelta(hours=7))
# Đơn cũ hơn mốc thread_id này là dữ liệu thời tiền-webapp, bỏ qua (như app gốc).
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
        vn = dt.astimezone(_VN_TZ)
        return vn.strftime("%Y-%m-%d"), vn.strftime("%d/%m %H:%M")
    except Exception:
        return None, ""


def orders_feed(conn, page: int, per_page: int, since_date, until_date,
                filter_product, filter_customer) -> dict:
    """Feed đơn + lợi nhuận phân trang cho bảng infinite-scroll của dashboard."""
    cur = conn.execute(
        "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL "
        "AND json IS NOT NULL AND thread_id >= ? ORDER BY thread_id DESC",
        (MIN_THREAD_ID,))

    all_orders = []
    for row in cur.fetchall():
        thread_id = row[0]
        order = json.loads(row[1])
        created = order.get("created", "")

        date_display = ""
        if created:
            created_date, date_display = _created_vn(created)
            if created_date is None:
                continue
            if since_date and created_date < since_date:
                continue
            if until_date and created_date > until_date:
                continue

        result = calculate_order_profit(conn, order)
        if not result["items"]:
            continue

        customer = str(resolve_customer_name(conn, order) or "")
        if filter_product and not any(i["code"] == filter_product for i in result["items"]):
            continue
        if filter_customer and filter_customer.lower() not in customer.lower():
            continue

        items_summary = [{k: item[k] for k in (
            "code", "qty", "sell_price", "cost_price", "revenue", "cost",
            "profit", "has_cost")} for item in result["items"]]

        all_orders.append({
            "thread_id": thread_id,
            "customer": customer[:30],
            "date": date_display,
            "revenue": result["total_revenue"],
            "cost": result["total_cost"],
            "profit": result["total_profit"],
            "has_cost": result["total_cost"] > 0,
            "items": items_summary,
            "fees": result.get("fees", {}),
            "order_text": (order.get("text") or "").strip()[:80],
        })

    start = (page - 1) * per_page
    end = start + per_page
    return {"orders": all_orders[start:end], "page": page,
            "has_more": end < len(all_orders), "total": len(all_orders)}


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
        order["invoice"] = freeze_invoice_cost_prices(conn, invoice)
        if _save_order(conn, thread_id, order):
            updated += 1
    return updated
