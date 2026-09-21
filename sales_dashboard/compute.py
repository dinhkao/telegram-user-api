"""Tính toán thuần cho dashboard bán hàng.

Số liệu lấy cùng nguồn với báo cáo lợi nhuận: toàn bộ đơn theo ngày tạo giờ Việt
Nam và phiếu trả đã xác nhận. Doanh thu/SL thuần đã trừ hàng trả; các chỉ số bán
gộp vẫn được giữ riêng để người dùng đối chiếu.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from product_db import get_all_products
from profit_dashboard.compute import scan_orders


def _pct(current: float, previous: float) -> float | None:
    if previous == 0:
        return 0.0 if current == 0 else None
    return round((current - previous) / abs(previous) * 100, 1)


def _rows_in(rows: list[dict], start: date, end: date) -> list[dict]:
    since, until = start.isoformat(), end.isoformat()
    return [row for row in rows if since <= row["ymd"] <= until]


def _previous_range(start: date, end: date) -> tuple[date, date]:
    days = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    return previous_end - timedelta(days=days - 1), previous_end


def _summary(rows: list[dict]) -> dict:
    sales = [row for row in rows if row["kind"] == "sale"]
    returns = [row for row in rows if row["kind"] == "return"]
    sale_items = [item for row in sales for item in row["items"]]
    return_items = [item for row in returns for item in row["items"]]
    gross_qty = sum(float(item.get("qty") or 0) for item in sale_items)
    return_qty = -sum(float(item.get("qty") or 0) for item in return_items)
    gross_revenue = sum(float(row.get("revenue") or 0) for row in sales)
    return_revenue = -sum(float(row.get("revenue") or 0) for row in returns)
    customers = {row["customer"] for row in sales}
    products = {item.get("code") for item in sale_items if item.get("code")}
    return {
        "net_qty": gross_qty - return_qty,
        "gross_qty": gross_qty,
        "return_qty": return_qty,
        "revenue": gross_revenue - return_revenue,
        "gross_revenue": gross_revenue,
        "return_revenue": return_revenue,
        "orders": len(sales),
        "returns": len(returns),
        "customers": len(customers),
        "products": len(products),
        "avg_order_value": round(gross_revenue / len(sales)) if sales else 0,
    }


def _period(rows: list[dict], start: date, end: date,
            previous_start: date | None = None, previous_end: date | None = None) -> dict:
    if previous_start is None or previous_end is None:
        previous_start, previous_end = _previous_range(start, end)
    current = _summary(_rows_in(rows, start, end))
    previous = _summary(_rows_in(rows, previous_start, previous_end))
    keys = ("net_qty", "revenue", "orders", "customers", "avg_order_value")
    return {
        "since": start.isoformat(),
        "until": end.isoformat(),
        "previous_since": previous_start.isoformat(),
        "previous_until": previous_end.isoformat(),
        "summary": current,
        "previous": previous,
        "changes": {key: _pct(current[key], previous[key]) for key in keys},
    }


def _daily(rows: list[dict], start: date, end: date) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for row in _rows_in(rows, start, end):
        buckets.setdefault(row["ymd"], []).append(row)
    return [
        {"day": day.isoformat(), **_summary(buckets.get(day.isoformat(), []))}
        for i in range((end - start).days + 1)
        for day in [start + timedelta(days=i)]
    ]


def _top_products(conn, rows: list[dict]) -> list[dict]:
    product_info = {item["code"]: item for item in get_all_products(conn)}
    grouped: dict[str, dict] = {}
    for row in rows:
        for item in row["items"]:
            code = str(item.get("code") or "").strip()
            if not code:
                continue
            value = grouped.setdefault(code, {
                "code": code, "gross_qty": 0.0, "return_qty": 0.0,
                "net_qty": 0.0, "revenue": 0.0, "orders": set(), "customers": set(),
            })
            qty = float(item.get("qty") or 0)
            value["net_qty"] += qty
            value["revenue"] += float(item.get("revenue") or 0)
            if row["kind"] == "sale":
                value["gross_qty"] += qty
                value["orders"].add(row["entry_id"])
                value["customers"].add(row["customer"])
            else:
                value["return_qty"] += -qty
    result = []
    for code, value in grouped.items():
        result.append({
            **{key: val for key, val in value.items() if key not in ("orders", "customers")},
            "name": (product_info.get(code) or {}).get("name") or "",
            "orders": len(value["orders"]),
            "customers": len(value["customers"]),
        })
    return sorted(result, key=lambda item: (item["revenue"], item["net_qty"]), reverse=True)


def _top_customers(rows: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for row in rows:
        name = row["customer"]
        value = grouped.setdefault(name, {
            "name": name, "gross_qty": 0.0, "return_qty": 0.0,
            "net_qty": 0.0, "revenue": 0.0, "orders": set(), "products": set(),
        })
        value["revenue"] += float(row.get("revenue") or 0)
        for item in row["items"]:
            qty = float(item.get("qty") or 0)
            value["net_qty"] += qty
            if row["kind"] == "sale":
                value["gross_qty"] += qty
                value["products"].add(item.get("code"))
            else:
                value["return_qty"] += -qty
        if row["kind"] == "sale":
            value["orders"].add(row["entry_id"])
    result = [{
        **{key: val for key, val in value.items() if key not in ("orders", "products")},
        "orders": len(value["orders"]),
        "products": len({code for code in value["products"] if code}),
    } for value in grouped.values()]
    return sorted(result, key=lambda item: (item["revenue"], item["net_qty"]), reverse=True)


def today_sales_summary(conn, today: str) -> dict:
    """KPI bán hàng trong ngày cho lối tắt ở Order Dashboard.

    Endpoint gọi hàm này chỉ trả ``_summary`` — không trả giá vốn/lợi nhuận dù
    nguồn quét dùng chung với dashboard lợi nhuận.
    """
    coverage = Counter()
    rows = scan_orders(conn, today, today, quality=coverage)
    return {
        "today": today,
        "summary": _summary(rows),
        "coverage": {
            **dict(coverage),
            "quality_errors": any(coverage[key] for key in (
                "invalid_orders", "undated_orders", "invalid_returns", "undated_returns",
                "return_amount_mismatches",
            )),
            "basis": "all_local_orders_by_created_date_vn",
        },
    }


def sales_dashboard_data(conn, since: str, until: str, today: str) -> dict:
    """Trả KPI nhanh + chi tiết một kỳ, chỉ quét bảng đơn một lần."""
    selected_start, selected_end = date.fromisoformat(since), date.fromisoformat(until)
    current_day = date.fromisoformat(today)

    # Chọn đúng 1 ngày: KPI vẫn là ngày đó, riêng biểu đồ mở ra trọn tuần để có
    # ngữ cảnh so sánh và cho frontend highlight ngày đang xem.
    chart_start, chart_end = selected_start, selected_end
    chart_selected_day = None
    if selected_start == selected_end:
        chart_start = selected_start - timedelta(days=selected_start.weekday())
        chart_end = chart_start + timedelta(days=6)
        chart_selected_day = selected_start.isoformat()

    week_start = current_day - timedelta(days=current_day.weekday())
    previous_week_start = week_start - timedelta(days=7)
    previous_week_end = previous_week_start + timedelta(days=current_day.weekday())

    month_start = current_day.replace(day=1)
    previous_month_end = month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    previous_month_same_day = previous_month_start + timedelta(
        days=min(current_day.day, previous_month_end.day) - 1)

    selected_previous = _previous_range(selected_start, selected_end)
    ranges = [
        (selected_start, selected_end), selected_previous, (chart_start, chart_end),
        (current_day, current_day), (current_day - timedelta(days=1), current_day - timedelta(days=1)),
        (week_start, current_day), (previous_week_start, previous_week_end),
        (month_start, current_day), (previous_month_start, previous_month_same_day),
    ]
    scan_start = min(start for start, _ in ranges)
    scan_end = max(end for _, end in ranges)
    coverage = Counter()
    rows = scan_orders(conn, scan_start.isoformat(), scan_end.isoformat(), quality=coverage)

    selected_rows = _rows_in(rows, selected_start, selected_end)
    quality_errors = any(coverage[key] for key in (
        "invalid_orders", "undated_orders", "invalid_returns", "undated_returns",
        "return_amount_mismatches",
    ))
    coverage = dict(coverage)
    coverage["quality_errors"] = quality_errors
    coverage["basis"] = "all_local_orders_by_created_date_vn"

    return {
        "today": current_day.isoformat(),
        "headline": {
            "today": _period(rows, current_day, current_day,
                             current_day - timedelta(days=1), current_day - timedelta(days=1)),
            "week": _period(rows, week_start, current_day, previous_week_start, previous_week_end),
            "month": _period(rows, month_start, current_day,
                              previous_month_start, previous_month_same_day),
        },
        "selected": {
            **_period(rows, selected_start, selected_end, *selected_previous),
            "daily": _daily(rows, chart_start, chart_end),
            "chart_since": chart_start.isoformat(),
            "chart_until": chart_end.isoformat(),
            "chart_selected_day": chart_selected_day,
            "top_products": _top_products(conn, selected_rows),
            "top_customers": _top_customers(selected_rows),
        },
        "coverage": coverage,
    }
