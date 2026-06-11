"""profit_dashboard.py — Web dashboard for profit analysis.

Runs on a separate port (default 8091) and shows:
- Product list with cost prices
- Profit per order
- Profit per product line
- Overall profit summary
- Customer profit analysis
- Export CSV
"""
from __future__ import annotations
import csv
import io
import calendar
import json
import logging
import os
from aiohttp import web
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

from order_db import _get_connection, get_order_by_thread_id
from what_data import USER_NAMES
from product_db import (
    create_products_table,
    migrate_products_table,
    get_product,
    get_all_products,
    upsert_product,
    delete_product,
    calculate_order_profit,
    get_products_from_orders,
)

log = logging.getLogger("profit_dashboard")

DASHBOARD_PORT = int(os.getenv("PROFIT_DASHBOARD_PORT", "8091"))

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "profit_settings.json")


DEFAULT_WEIGHTS = {str(m): 1.0 for m in range(1, 13)}


def load_settings():
    """Load dashboard settings from JSON file, ensuring weights exist."""
    default = {"yearly_loan_payment": 0, "monthly_weights": dict(DEFAULT_WEIGHTS)}
    if not os.path.exists(SETTINGS_FILE):
        return default
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Backward compat: convert monthly to yearly
        if "yearly_loan_payment" not in data:
            if "monthly_loan_payment" in data:
                data["yearly_loan_payment"] = data["monthly_loan_payment"] * 12
                del data["monthly_loan_payment"]
            else:
                data["yearly_loan_payment"] = 0
        # Backfill weights if missing
        if "monthly_weights" not in data:
            data["monthly_weights"] = dict(DEFAULT_WEIGHTS)
        else:
            # Ensure all 12 months present
            for m in range(1, 13):
                data["monthly_weights"].setdefault(str(m), 1.0)
        return data
    except:
        return default


def save_settings(settings):
    """Save dashboard settings to JSON file."""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        log.error(f"Failed to save settings: {e}")
        return False


def calc_prorated_loan(since_date, until_date, base_monthly_loan, weights=None):
    """Calculate loan allocation for a date range using monthly weights.

    Each month M gets: base_monthly_loan * weight[M] / avg_weight
    Prorated by actual overlap days within that month.
    """
    if base_monthly_loan <= 0:
        return 0
    if weights is None:
        weights = DEFAULT_WEIGHTS
    # Ensure all 12 months have a weight
    w = {str(m): float(weights.get(str(m), weights.get(m, 1.0))) for m in range(1, 13)}
    avg_weight = sum(w.values()) / 12.0
    if avg_weight <= 0:
        return 0

    total = 0.0
    current = since_date
    while current <= until_date:
        days_in_month = calendar.monthrange(current.year, current.month)[1]
        month_start = current.replace(day=1)
        month_end = current.replace(day=days_in_month)
        overlap_start = max(current, month_start)
        overlap_end = min(until_date, month_end)
        overlap_days = (overlap_end - overlap_start).days + 1
        monthly_amount = base_monthly_loan * w[str(current.month)] / avg_weight
        total += monthly_amount * overlap_days / days_in_month
        # advance to first day of next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1, day=1)
        else:
            current = current.replace(month=current.month + 1, day=1)
    return int(total)

def _format_money(n: int) -> str:
    return f"{n:,}"


def _get_date_presets_html():
    """Generate HTML for quick date preset buttons."""
    return """
                <div class="presets">
                    <button type="button" onclick="setDatePreset('today')">Hôm nay</button>
                    <button type="button" onclick="setDatePreset('yesterday')">Hôm qua</button>
                    <button type="button" onclick="setDatePreset('this_week')">Tuần này</button>
                    <button type="button" onclick="setDatePreset('7days')">7 ngày</button>
                    <button type="button" onclick="setDatePreset('14days')">14 ngày</button>
                    <button type="button" onclick="setDatePreset('30days')">30 ngày</button>
                    <button type="button" onclick="setDatePreset('this_month')">Tháng này</button>
                    <button type="button" onclick="setDatePreset('last_month')">Tháng trước</button>
                </div>"""


def generate_dashboard_html(db_conn, filter_product=None, filter_customer=None, limit=500, since_date=None, until_date=None, yearly_loan=0, monthly_weights=None):
    """Generate the main dashboard HTML."""
    
    # Get all products
    products = get_all_products(db_conn)
    product_map = {p["code"]: p for p in products}
    
    # Get orders with profit (use thread_id for sorting as it's sequential)
    cur = db_conn.execute(
        "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL "
        "AND json IS NOT NULL AND thread_id BETWEEN 460000 AND 480000 "
        "ORDER BY thread_id DESC LIMIT ?",
        (limit,)
    )
    
    orders_data = []
    total_revenue = 0
    total_cost = 0
    total_profit = 0
    product_profit_map = {}  # code -> {qty, revenue, cost, profit}
    
    # Default: orders from May 1, 2026
    if since_date is None:
        since_date = "2026-05-01"
    
    for row in cur.fetchall():
        thread_id = row[0]
        order = json.loads(row[1])
        
        # Filter by date range (VN timezone UTC+7)
        created = order.get("created", "")
        if created:
            try:
                vn_tz = timezone(timedelta(hours=7))
                if isinstance(created, str):
                    dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                    created_date = dt.astimezone(vn_tz).strftime("%Y-%m-%d")
                elif created > 1e10:
                    created_date = datetime.fromtimestamp(created / 1000, tz=timezone.utc).astimezone(vn_tz).strftime("%Y-%m-%d")
                else:
                    created_date = datetime.fromtimestamp(created, tz=timezone.utc).astimezone(vn_tz).strftime("%Y-%m-%d")
                if since_date and created_date < since_date:
                    continue
                if until_date and created_date > until_date:
                    continue
            except:
                continue
        
        result = calculate_order_profit(db_conn, order)
        if not result["items"]:
            continue
        
        customer = order.get("customer_name") or order.get("khach_hang") or ""
        # Extract name if customer is a dict
        if isinstance(customer, dict):
            customer = customer.get("name", "")
        customer = str(customer or "")
        
        # Filter by product if specified
        if filter_product:
            has_product = any(item["code"] == filter_product for item in result["items"])
            if not has_product:
                continue
        
        # Filter by customer if specified
        if filter_customer and filter_customer.lower() not in customer.lower():
            continue
        
        orders_data.append({
            "thread_id": thread_id,
            "customer": customer,
            "created": created,
            "revenue": result["total_revenue"],
            "cost": result["total_cost"],
            "profit": result["total_profit"],
            "items": result["items"],
            "items_with_cost": result["items_with_cost"],
            "item_count": result["item_count"],
        })
        
        total_revenue += result["total_revenue"]
        total_cost += result["total_cost"]
        total_profit += result["total_profit"]
        
        # Aggregate by product
        for item in result["items"]:
            code = item["code"]
            if code not in product_profit_map:
                product_profit_map[code] = {"qty": 0, "revenue": 0, "cost": 0, "profit": 0}
            product_profit_map[code]["qty"] += item["qty"]
            product_profit_map[code]["revenue"] += item["revenue"]
            product_profit_map[code]["cost"] += item["cost"]
            product_profit_map[code]["profit"] += item["profit"]
    
    # Sort orders by newest first (thread_id descending)
    orders_data.sort(key=lambda x: x["thread_id"], reverse=True)
    
    # Sort products by profit
    product_summary = sorted(product_profit_map.items(), key=lambda x: x[1]["profit"], reverse=True)
    
    # Calculate previous period for comparison
    try:
        vn_tz = timezone(timedelta(hours=7))
        try:
            end_date = datetime.strptime(until_date, "%Y-%m-%d").date() if until_date else datetime.now(vn_tz).date()
        except (ValueError, TypeError):
            end_date = datetime.now(vn_tz).date()
        try:
            start_date = datetime.strptime(since_date, "%Y-%m-%d").date() if since_date else datetime.strptime("2026-05-01", "%Y-%m-%d").date()
        except (ValueError, TypeError):
            start_date = datetime.strptime("2026-05-01", "%Y-%m-%d").date()
        
        # Validate date range
        if end_date < start_date:
            end_date = start_date
        
        period_days = (end_date - start_date).days + 1
        
        # Previous period: same length, shifted back
        prev_end = start_date - timedelta(days=1)
        prev_start = prev_end - timedelta(days=period_days - 1)
        
        # Query previous period orders
        prev_cur = db_conn.execute(
            "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL "
            "AND json IS NOT NULL AND thread_id BETWEEN 460000 AND 480000 "
            "ORDER BY thread_id DESC LIMIT 1000"
        )
        
        prev_revenue = 0
        prev_cost = 0
        prev_profit = 0
        prev_orders = 0
        prev_customer_profit = {}
        prev_product_profit = {}
        
        for row in prev_cur.fetchall():
            order = json.loads(row[1])
            created = order.get("created", "")
            if not created:
                continue
            try:
                if isinstance(created, str):
                    dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                elif created > 1e10:
                    dt = datetime.fromtimestamp(created / 1000, tz=timezone.utc)
                else:
                    dt = datetime.fromtimestamp(created, tz=timezone.utc)
                created_date = dt.astimezone(vn_tz).date()
                if created_date < prev_start or created_date > prev_end:
                    continue
            except:
                continue
            
            result = calculate_order_profit(db_conn, order)
            if not result["items"]:
                continue
            
            prev_revenue += result["total_revenue"]
            prev_cost += result["total_cost"]
            prev_profit += result["total_profit"]
            prev_orders += 1
            
            # Track customers (consistent handling)
            customer = order.get("customer_name") or order.get("khach_hang") or ""
            if isinstance(customer, dict):
                customer = customer.get("name", "")
            customer = str(customer or "").strip() or "Khách lẻ"
            if customer not in prev_customer_profit:
                prev_customer_profit[customer] = {"revenue": 0, "profit": 0, "orders": 0}
            prev_customer_profit[customer]["revenue"] += result["total_revenue"]
            prev_customer_profit[customer]["profit"] += result["total_profit"]
            prev_customer_profit[customer]["orders"] += 1
            
            # Track products
            for item in result["items"]:
                code = item["code"]
                if code not in prev_product_profit:
                    prev_product_profit[code] = {"qty": 0, "profit": 0}
                prev_product_profit[code]["qty"] += item["qty"]
                prev_product_profit[code]["profit"] += item["profit"]
        
        # Calculate percentage changes
        def pct_change(current, previous):
            if previous == 0:
                return None  # Signal for "new" data
            return ((current - previous) / previous) * 100
        
        revenue_change = pct_change(total_revenue, prev_revenue)
        cost_change = pct_change(total_cost, prev_cost)
        profit_change = pct_change(total_profit, prev_profit)
        orders_change = pct_change(len(orders_data), prev_orders)
        
        # Top performers - use unfiltered data to show overall top performers
        # Need to re-query to get all customers in the period (not filtered by product/customer)
        top_customers_current = {}
        top_products_current = {}
        
        # Re-query current period for top performers
        curr_cur = db_conn.execute(
            "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL "
            "AND json IS NOT NULL AND thread_id BETWEEN 460000 AND 480000 "
            "ORDER BY thread_id DESC LIMIT 2000"
        )
        
        for row in curr_cur.fetchall():
            order = json.loads(row[1])
            created = order.get("created", "")
            if not created:
                continue
            try:
                if isinstance(created, str):
                    dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                elif created > 1e10:
                    dt = datetime.fromtimestamp(created / 1000, tz=timezone.utc)
                else:
                    dt = datetime.fromtimestamp(created, tz=timezone.utc)
                created_date = dt.astimezone(vn_tz).date()
                if created_date < start_date or created_date > end_date:
                    continue
            except:
                continue
            
            result = calculate_order_profit(db_conn, order)
            if not result["items"]:
                continue
            
            # Track customers (consistent handling)
            customer = order.get("customer_name") or order.get("khach_hang") or ""
            if isinstance(customer, dict):
                customer = customer.get("name", "")
            customer = str(customer or "").strip() or "Khách lẻ"
            if customer not in top_customers_current:
                top_customers_current[customer] = {"revenue": 0, "profit": 0, "orders": 0}
            top_customers_current[customer]["revenue"] += result["total_revenue"]
            top_customers_current[customer]["profit"] += result["total_profit"]
            top_customers_current[customer]["orders"] += 1
            
            # Track products
            for item in result["items"]:
                code = item["code"]
                if code not in top_products_current:
                    top_products_current[code] = {"qty": 0, "revenue": 0, "profit": 0}
                top_products_current[code]["qty"] += item["qty"]
                top_products_current[code]["revenue"] += item["revenue"]
                top_products_current[code]["profit"] += item["profit"]
        
        top_customers = sorted(top_customers_current.items(), key=lambda x: x[1]["profit"], reverse=True)[:5]
        top_products = sorted(top_products_current.items(), key=lambda x: x[1]["profit"], reverse=True)[:5]
        
        prev_period_label = f"{prev_start.strftime('%d/%m')} - {prev_end.strftime('%d/%m')}"
        curr_period_label = f"{start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m')}"
    except Exception as e:
        revenue_change = cost_change = profit_change = orders_change = 0
        prev_revenue = prev_cost = prev_profit = prev_orders = 0
        top_customers = []
        top_products = []
        prev_period_label = "kỳ trước"
        curr_period_label = "kỳ này"
    
    # Calculate prorated loan payment using monthly weights
    base_monthly = yearly_loan / 12.0
    prorated_loan = 0
    if base_monthly > 0:
        try:
            vn_tz = timezone(timedelta(hours=7))
            period_end = datetime.strptime(until_date, "%Y-%m-%d").date() if until_date else datetime.now(vn_tz).date()
            period_start = datetime.strptime(since_date, "%Y-%m-%d").date() if since_date else datetime.strptime("2026-05-01", "%Y-%m-%d").date()
            prorated_loan = calc_prorated_loan(period_start, period_end, base_monthly, monthly_weights)
        except:
            prorated_loan = int(base_monthly)
    
    real_profit = total_profit - prorated_loan
    profit_margin = (real_profit / total_revenue * 100) if total_revenue > 0 else 0
    
    # Aggregate profit by day for chart (VN timezone)
    daily = {}
    for od in orders_data:
        created = od.get('created', '') or ''
        if not created:
            continue
        # Convert to VN timezone for correct day grouping
        try:
            if isinstance(created, str):
                dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
            elif created > 1e10:
                dt = datetime.fromtimestamp(created / 1000, tz=timezone.utc)
            else:
                dt = datetime.fromtimestamp(created, tz=timezone.utc)
            vn = dt.astimezone(timezone(timedelta(hours=7)))
            day = vn.strftime("%Y-%m-%d")
        except:
            day = created[:10] if isinstance(created, str) else ""
        if not day:
            continue
        daily.setdefault(day, {"revenue": 0, "cost": 0, "profit": 0})
        daily[day]["revenue"] += od["revenue"]
        daily[day]["cost"] += od["cost"]
        daily[day]["profit"] += od["profit"]
    chart_days = sorted(daily.keys())
    
    # Calculate daily loan allocation for chart
    daily_loan = {}
    if base_monthly > 0 and chart_days:
        for d in chart_days:
            try:
                day_date = datetime.strptime(d, "%Y-%m-%d").date()
                daily_loan[d] = calc_prorated_loan(day_date, day_date, base_monthly, monthly_weights)
            except:
                daily_loan[d] = 0
    
    chart_data = json.dumps([{
        "day": d[-5:],  # MM-DD
        "full_day": d,
        "revenue": daily[d]["revenue"],
        "cost": daily[d]["cost"],
        "profit": daily[d]["profit"],
        "real_profit": daily[d]["profit"] - daily_loan.get(d, 0),
    } for d in chart_days[-60:]], ensure_ascii=False)  # Last 60 days
    
    # Build HTML
    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard Lợi Nhuận</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 10px; }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{ color: #333; margin-bottom: 16px; font-size: 22px; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 24px; }}
        .card {{ background: white; border-radius: 10px; padding: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; }}
        .card h3 {{ color: #666; font-size: 12px; margin-bottom: 6px; }}
        .card .value {{ font-size: 20px; font-weight: bold; }}
        .card .value.positive {{ color: #22c55e; }}
        .card .value.negative {{ color: #ef4444; }}
        .nav {{ margin-bottom: 16px; display: flex; flex-wrap: wrap; gap: 6px; }}
        .nav a {{ padding: 8px 12px; background: #3b82f6; color: white; text-decoration: none; border-radius: 5px; white-space: nowrap; font-size: 13px; }}
        .nav a:hover {{ background: #2563eb; }}
        .nav a.active {{ background: #1d4ed8; }}
        .filters {{ background: white; border-radius: 10px; padding: 12px; margin-bottom: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }}
        .filters input, .filters button {{ padding: 8px 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 13px; }}
        .filters input[type="date"] {{ width: auto; min-width: 120px; }}
        .filters input[type="text"] {{ width: auto; min-width: 100px; }}
        .filters button {{ background: #3b82f6; color: white; cursor: pointer; border: none; }}
        .filters button:hover {{ background: #2563eb; }}
        .presets {{ display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; Width: 100%; }}
        .presets button {{ padding: 5px 10px; background: #e5e7eb; color: #333; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; white-space: nowrap; }}
        .presets button:hover {{ background: #d1d5db; }}
        .presets button.active {{ background: #3b82f6; color: white; }}
        .filters a {{ padding: 8px 10px; text-decoration: none; color: #3b82f6; white-space: nowrap; font-size: 13px; }}
        .table-wrap {{ width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; background: white; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 24px; }}
        table {{ width: 100%; min-width: 600px; border-collapse: collapse; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; font-size: 14px; }}
        th {{ background: #f8f9fa; font-weight: 600; color: #333; white-space: nowrap; position: sticky; top: 0; }}
        tr:hover {{ background: #f5f5f5; }}
        tr {{ cursor: pointer; }}
        .profit {{ font-weight: 600; }}
        .profit.positive {{ color: #22c55e; }}
        .profit.negative {{ color: #ef4444; }}
        .tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; }}
        .tag.green {{ background: #dcfce7; color: #166534; }}
        .tag.red {{ background: #fee2e2; color: #991b1b; }}
        .tag.yellow {{ background: #fef9c3; color: #854d0e; }}
        .section {{ margin-bottom: 24px; }}
        .section h2 {{ color: #333; margin-bottom: 12px; font-size: 16px; }}
        
        /* Comparison indicators */
        .change {{ font-size: 12px; margin-top: 6px; font-weight: 600; display: flex; align-items: center; gap: 4px; justify-content: center; flex-wrap: wrap; }}
        .change.up {{ color: #22c55e; }}
        .change.down {{ color: #ef4444; }}
        .change.new {{ color: #3b82f6; }}
        .change-label {{ color: #999; font-weight: normal; font-size: 11px; }}
        
        /* Top Performers Widget */
        .top-performers {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }}
        
        /* Real Profit Card */
        .real-profit-card {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important; color: white; }}
        .real-profit-card h3 {{ color: rgba(255,255,255,0.9) !important; }}
        .real-profit-card .value {{ color: white !important; }}
        .loan-info {{ font-size: 11px; margin-top: 6px; opacity: 0.95; display: flex; flex-direction: column; gap: 2px; align-items: center; }}
        .margin-badge {{ background: rgba(255,255,255,0.2); padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 600; }}
        .performer-section {{ background: white; border-radius: 10px; padding: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .performer-section h3 {{ color: #333; margin-bottom: 12px; font-size: 15px; }}
        .performer-list {{ display: flex; flex-direction: column; gap: 8px; }}
        .performer-item {{ display: flex; align-items: center; gap: 12px; padding: 8px; border-radius: 6px; transition: background 0.2s; }}
        .performer-item:hover {{ background: #f8f9fa; }}
        .performer-rank {{ background: linear-gradient(135deg, #3b82f6, #1d4ed8); color: white; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 13px; flex-shrink: 0; }}
        .performer-item:nth-child(1) .performer-rank {{ background: linear-gradient(135deg, #fbbf24, #f59e0b); }}
        .performer-item:nth-child(2) .performer-rank {{ background: linear-gradient(135deg, #94a3b8, #64748b); }}
        .performer-item:nth-child(3) .performer-rank {{ background: linear-gradient(135deg, #fb923c, #ea580c); }}
        .performer-info {{ flex: 1; min-width: 0; }}
        .performer-name {{ font-weight: 600; color: #333; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .performer-stats {{ display: flex; gap: 12px; margin-top: 2px; font-size: 12px; color: #666; }}
        .empty-state {{ text-align: center; color: #999; padding: 20px; font-size: 13px; }}
        .tabs {{ display: flex; gap: 8px; margin-bottom: 16px; }}
        .tab {{ padding: 10px 16px; background: white; border: none; border-radius: 5px; cursor: pointer; font-size: 14px; }}
        .tab.active {{ background: #3b82f6; color: white; }}
        .tab:hover {{ background: #e5e7eb; }}
        .tab.active:hover {{ background: #2563eb; }}
        @media (max-width: 768px) {{
            body {{ padding: 8px; }}
            h1 {{ font-size: 18px; }}
            .summary {{ grid-template-columns: 1fr 1fr; gap: 8px; }}
            .card {{ padding: 12px; }}
            .card h3 {{ font-size: 11px; }}
            .card .value {{ font-size: 18px; }}
            .nav a {{ font-size: 12px; padding: 6px 10px; }}
            .filters {{ flex-direction: column; align-items: stretch; }}
            .filters input {{ width: 100% !important; }}
            .filters button {{ width: 100%; }}
            .tab {{ font-size: 13px; padding: 8px 12px; }}
            th, td {{ padding: 8px 10px; font-size: 13px; }}
            .top-performers {{ grid-template-columns: 1fr; gap: 12px; }}
        }}
        @media (max-width: 480px) {{
            .summary {{ grid-template-columns: 1fr 1fr; gap: 6px; }}
            .card .value {{ font-size: 16px; }}
            h1 {{ font-size: 16px; }}
        }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/" class="active">🏠 Dashboard</a>
            <a href="/customers">👥 Khách hàng</a>
            <a href="/export/orders">📥 Export Orders</a>
            <a href="/export/products">📥 Export Products</a>
            <a href="/settings">⚙️ Cấu hình</a>
        </div>
        <h1>📊 Dashboard Lợi Nhuận</h1>
        
        <div class="filters">
            <div class="presets">
                <button type="button" onclick="setDatePreset('today')">Hôm nay</button>
                <button type="button" onclick="setDatePreset('yesterday')">Hôm qua</button>
                <button type="button" onclick="setDatePreset('this_week')">Tuần này</button>
                <button type="button" onclick="setDatePreset('7days')">7 ngày</button>
                <button type="button" onclick="setDatePreset('14days')">14 ngày</button>
                <button type="button" onclick="setDatePreset('30days')">30 ngày</button>
                <button type="button" onclick="setDatePreset('this_month')">Tháng này</button>
                <button type="button" onclick="setDatePreset('last_month')">Tháng trước</button>
            </div>
            <form method="GET" action="/">
                <input type="date" name="since" id="since" value="{since_date or '2026-05-01'}" title="Từ ngày" onchange="this.form.submit()">
                <input type="date" name="until" id="until" value="{until_date or ''}" title="Đến ngày" onchange="this.form.submit()">
                <input type="text" name="product" placeholder="Lọc theo mã SP" value="{filter_product or ''}">
                <input type="text" name="customer" placeholder="Lọc theo khách hàng" value="{filter_customer or ''}">
                <button type="submit">🔍 Lọc</button>
                <a href="/" style="padding: 8px 12px; text-decoration: none; color: #3b82f6;">Xóa bộ lọc</a>
                <button type="button" onclick="freezeAllCosts()" style="padding: 8px 16px; background: #f59e0b; color: white; border: none; border-radius: 5px; cursor: pointer; margin-left: 10px;">🔒 Đóng băng giá vốn</button>
            </form>
        </div>
        
        <div class="summary">
            <div class="card">
                <h3>📦 Doanh thu</h3>
                <div class="value">{_format_money(total_revenue)}đ</div>
                <div class="change {'up' if revenue_change is not None and revenue_change >= 0 else 'down' if revenue_change is not None else 'new'}">
                    {f"🆕 Mới" if revenue_change is None else f"{'↑' if revenue_change >= 0 else '↓'} {abs(revenue_change):.1f}%"}
                    <span class="change-label">vs {prev_period_label}</span>
                </div>
            </div>
            <div class="card">
                <h3>💵 Giá vốn</h3>
                <div class="value">{_format_money(total_cost)}đ</div>
                <div class="change {'up' if cost_change is not None and cost_change >= 0 else 'down' if cost_change is not None else 'new'}">
                    {f"🆕 Mới" if cost_change is None else f"{'↑' if cost_change >= 0 else '↓'} {abs(cost_change):.1f}%"}
                    <span class="change-label">vs {prev_period_label}</span>
                </div>
            </div>
            <div class="card">
                <h3>💰 Lợi nhuận</h3>
                <div class="value {'positive' if total_profit >= 0 else 'negative'}">{_format_money(total_profit)}đ</div>
                <div class="change {'up' if profit_change is not None and profit_change >= 0 else 'down' if profit_change is not None else 'new'}">
                    {f"🆕 Mới" if profit_change is None else f"{'↑' if profit_change >= 0 else '↓'} {abs(profit_change):.1f}%"}
                    <span class="change-label">vs {prev_period_label}</span>
                </div>
            </div>
            <div class="card real-profit-card">
                <h3>💎 Lợi nhuận thực</h3>
                <div class="value {'positive' if real_profit >= 0 else 'negative'}">{_format_money(real_profit)}đ</div>
                <div class="loan-info">
                    <span>Trừ lãi vay: {_format_money(prorated_loan)}đ</span>
                    {f'<span class="margin-badge">Biên: {profit_margin:.1f}%</span>' if total_revenue > 0 else ''}
                </div>
            </div>
            <div class="card">
                <h3>📋 Đơn hàng</h3>
                <div class="value">{len(orders_data)}</div>
                <div class="change {'up' if orders_change is not None and orders_change >= 0 else 'down' if orders_change is not None else 'new'}">
                    {f"🆕 Mới" if orders_change is None else f"{'↑' if orders_change >= 0 else '↓'} {abs(orders_change):.1f}%"}
                    <span class="change-label">vs {prev_period_label}</span>
                </div>
            </div>
        </div>
        
        <!-- Top Performers Widget -->
        <div class="top-performers">
            <div class="performer-section">
                <h3>🏆 Top 5 Khách hàng VIP</h3>
                <div class="performer-list">
                    {''.join(f'''
                    <div class="performer-item" onclick="location.href='/customer/{quote(cust)}'" style="cursor: pointer;">
                        <div class="performer-rank">{i+1}</div>
                        <div class="performer-info">
                            <div class="performer-name">{cust[:30]}</div>
                            <div class="performer-stats">
                                <span>📦 {data["orders"]} đơn</span>
                                <span>💰 {_format_money(data["profit"])}đ</span>
                            </div>
                        </div>
                    </div>
                    ''' for i, (cust, data) in enumerate(top_customers)) if top_customers else '<div class="empty-state">Chưa có dữ liệu</div>'}
                </div>
            </div>
            <div class="performer-section">
                <h3>⭐ Top 5 Sản phẩm lợi nhuận cao</h3>
                <div class="performer-list">
                    {''.join(f'''
                    <div class="performer-item">
                        <div class="performer-rank">{i+1}</div>
                        <div class="performer-info">
                            <div class="performer-name">{code}</div>
                            <div class="performer-stats">
                                <span>📊 {pdata["qty"]} sp</span>
                                <span>💰 {_format_money(pdata["profit"])}đ</span>
                            </div>
                        </div>
                    </div>
                    ''' for i, (code, pdata) in enumerate(top_products)) if top_products else '<div class="empty-state">Chưa có dữ liệu</div>'}
                </div>
            </div>
        </div>
        
        <div class="tabs">
            <button class="tab active" onclick="showTab('orders')">Đơn hàng</button>
            <button class="tab" onclick="showTab('products')">Sản phẩm</button>
            <button class="tab" onclick="showTab('chart')">Biểu đồ</button>
        </div>
        
        <div id="orders-tab" class="section">
            <h2>📋 Lợi nhuận theo đơn hàng</h2>
            <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>Đơn hàng</th>
                        <th>Ngày</th>
                        <th>Khách hàng</th>
                        <th>Sản phẩm</th>
                        <th>Doanh thu</th>
                        <th>Giá vốn</th>
                        <th>Lợi nhuận</th>
                        <th>Biên LN</th>
                    </tr>
                </thead>
                <tbody>"""
    
    # Add order rows
    for od in orders_data[:100]:
        has_cost = od["cost"] > 0
        profit_class = "positive" if od["profit"] > 0 else ("negative" if od["profit"] < 0 else "")
        margin = (od["profit"] / od["revenue"] * 100) if od["revenue"] > 0 and has_cost else 0
        profit_display = f'{_format_money(od["profit"])}đ' if has_cost else '<span class="tag yellow">Chưa có giá vốn</span>'
        
        customer_name = (od['customer'] or '')[:30]
        customer_url = quote(od['customer'] or '')
        # Format date + time (convert to VN timezone UTC+7)
        created = od.get('created', '')
        if created:
            try:
                vn_tz = timezone(timedelta(hours=7))
                if isinstance(created, str):
                    dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                    vn = dt.astimezone(vn_tz)
                    date_display = vn.strftime("%d/%m %H:%M")
                elif created > 1e10:
                    dt = datetime.fromtimestamp(created / 1000, tz=timezone.utc)
                    vn = dt.astimezone(vn_tz)
                    date_display = vn.strftime("%d/%m %H:%M")
                else:
                    dt = datetime.fromtimestamp(created, tz=timezone.utc)
                    vn = dt.astimezone(vn_tz)
                    date_display = vn.strftime("%d/%m %H:%M")
            except:
                date_display = ""
        else:
            date_display = ""
        
        # Build product details
        items = od.get('items', [])
        product_details = []
        for item in items:
            code = item.get('code', '?')
            qty = item.get('qty', 0)
            cost_price = item.get('cost_price', 0)
            has_item_cost = item.get('has_cost', False)
            if has_item_cost:
                product_details.append(f"{code}({qty})")
            else:
                product_details.append(f"<span style='color:#f59e0b'>{code}({qty})</span>")
        products_html = "<br>".join(product_details) if product_details else "-"
        
        # Build items JSON for modal - escape for HTML attribute
        items_json = json.dumps(items).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace(chr(39), '&#39;')
        
        # Get fees for the order
        vat = int(order.get("vat", 0))
        pvc = int(order.get("pvc", 0))
        disc = int(order.get("discount", 0))
        fees_obj = {"vat": vat, "pvc": pvc, "discount": disc}
        fees_json = json.dumps(fees_obj).replace('"', '&quot;').replace(chr(39), '&#39;')
        
        html += f"""
                    <tr onclick="showOrderDetail({od['thread_id']}, &#39;{customer_name}&#39;, &#39;{date_display}&#39;, {od['revenue']}, {od['cost']}, {od['profit']}, {items_json}, {fees_json})" style="cursor: pointer;">
                        <td><a href="tg://privatepost?channel=2124542200&post={od['thread_id']}" target="_blank" onclick="event.stopPropagation()">#{od['thread_id']}</a></td>
                        <td>{date_display}</td>
                        <td><a href="/customer/{customer_url}" style="color: #3b82f6; text-decoration: none;" onclick="event.stopPropagation()">{customer_name}</a></td>
                        <td style="font-size: 12px;">{products_html}</td>
                        <td>{_format_money(od['revenue'])}đ</td>
                        <td>{_format_money(od['cost'])}đ</td>
                        <td class="profit {profit_class}">{profit_display}</td>
                        <td>{margin:.1f}%</td>
                    </tr>"""
    
    html += """
                    <tr id="loading-row" style="display:none;">
                        <td colspan="8" style="text-align:center; padding: 20px;">
                            <div class="spinner"></div> Đang tải thêm...
                        </td>
                    </tr>
                </tbody>
            </table>
            </div>
        </div>
        
        <div id="products-tab" class="section" style="display:none">
            <h2>📦 Lợi nhuận theo sản phẩm</h2>
            <form method="POST" action="/products/bulk-update">
                <div style="margin-bottom: 10px;">
                    <button type="submit" style="padding: 8px 16px; background: #22c55e; color: white; border: none; border-radius: 5px; cursor: pointer;">💾 Lưu tất cả giá vốn</button>
                    <button type="button" onclick="selectAllWithCost()" style="padding: 8px 16px; background: #3b82f6; color: white; border: none; border-radius: 5px; cursor: pointer; margin-left: 10px;">Chọn SP chưa có giá vốn</button>
                </div>
                <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Mã SP</th>
                            <th>Giá vốn hiện tại</th>
                            <th>Giá vốn mới</th>
                            <th>SL bán</th>
                            <th>Doanh thu</th>
                            <th>Lợi nhuận</th>
                            <th>Thao tác</th>
                        </tr>
                    </thead>
                    <tbody>"""
    
    # Add product rows
    for code, pdata in product_summary[:100]:
        product = product_map.get(code, {})
        cost_price = product.get("cost_price", 0)
        has_cost = cost_price > 0
        
        profit_class = "positive" if pdata["profit"] >= 0 else "negative"
        cost_tag = f'<span class="tag green">{_format_money(cost_price)}đ</span>' if has_cost else '<span class="tag yellow">Chưa có</span>'
        
        html += f"""
                    <tr id="row-{code}">
                        <td><strong>{code}</strong></td>
                        <td>{cost_tag}</td>
                        <td><input type="number" name="cost_{code}" value="{cost_price if has_cost else ''}" placeholder="Nhập giá" style="width: 100px; padding: 4px;" {'class="no-cost"' if not has_cost else ''}></td>
                        <td>{pdata['qty']}</td>
                        <td>{_format_money(pdata['revenue'])}đ</td>
                        <td class="profit {profit_class}">{_format_money(pdata['profit'])}đ</td>
                        <td><a href="/product/{code}">Chi tiết</a></td>
                    </tr>"""
    
    html += """
                    </tbody>
                </table>
                </div>
            </form>
        </div>
    </div>
    
    <div id="chart-tab" class="section" style="display:none">
        <h2>📊 Biểu đồ lợi nhuận theo ngày</h2>
        <div style="background:white; border-radius:10px; padding:20px; box-shadow:0 2px 10px rgba(0,0,0,0.1);">
            <canvas id="profitChart" style="width:100%; max-height:400px;"></canvas>
        </div>
    </div>
    
    <!-- Order Detail Modal -->
    <div id="orderModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1000; overflow:auto;">
        <div class="modal-content" style="background:white; margin:40px auto; max-width:95%; width:700px; border-radius:10px; padding:16px; position:relative;">
            <button onclick="closeModal()" style="position:absolute; top:8px; right:12px; background:none; border:none; font-size:28px; cursor:pointer; line-height:1; padding:4px;">✕</button>
            <h2 id="modal-title" style="margin-bottom:16px; font-size:18px;">Chi tiết đơn hàng</h2>
            <div id="modal-content" style="overflow-x:auto;"></div>
        </div>
    </div>
    
    <script>
    function selectAllWithCost() {
        document.querySelectorAll('input.no-cost').forEach(el => el.focus());
    }
    </script>
    <style>
        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #3b82f6;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            animation: spin 1s linear infinite;
            display: inline-block;
            margin-right: 10px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    </style>
    <script>
    function showTab(tab) {
        document.getElementById('orders-tab').style.display = tab === 'orders' ? 'block' : 'none';
        document.getElementById('products-tab').style.display = tab === 'products' ? 'block' : 'none';
        document.getElementById('chart-tab').style.display = tab === 'chart' ? 'block' : 'none';
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        event.target.classList.add('active');
        if (tab === 'chart') renderChart();
    }
    
    // Chart data from server
    let profitChart = null;
    const chartData = __CHART_DATA__;
    
    function renderChart() {
        if (profitChart) return;
        const ctx = document.getElementById('profitChart').getContext('2d');
        const days = chartData.map(d => d.day);
        profitChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: days,
                datasets: [
                    {
                        label: 'Doanh thu',
                        data: chartData.map(d => d.revenue),
                        backgroundColor: 'rgba(59, 130, 246, 0.7)',
                        borderColor: '#3b82f6',
                        borderWidth: 1
                    },
                    {
                        label: 'Giá vốn',
                        data: chartData.map(d => d.cost),
                        backgroundColor: 'rgba(239, 68, 68, 0.5)',
                        borderColor: '#ef4444',
                        borderWidth: 1
                    },
                    {
                        label: 'Lợi nhuận',
                        data: chartData.map(d => d.profit),
                        backgroundColor: 'rgba(34, 197, 94, 0.7)',
                        borderColor: '#22c55e',
                        borderWidth: 1
                    },
                    {
                        label: 'Lợi nhuận sau vay',
                        data: chartData.map(d => d.real_profit),
                        backgroundColor: 'rgba(168, 85, 247, 0.7)',
                        borderColor: '#a855f7',
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top' },
                    tooltip: {
                        callbacks: {
                            label: ctx => ctx.dataset.label + ': ' + ctx.raw.toLocaleString() + 'đ'
                        }
                    }
                },
                scales: {
                    y: {
                        ticks: {
                            callback: v => (v / 1000000).toFixed(1) + 'M'
                        }
                    }
                }
            }
        });
    }
    
    // Check URL params for tab
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('tab') === 'products') {
        showTab('products');
        document.querySelectorAll('.tab')[1].classList.add('active');
    }
    if (urlParams.get('tab') === 'chart') {
        showTab('chart');
        document.querySelectorAll('.tab')[2].classList.add('active');
    }
    
    // Quick date presets
    function setDatePreset(preset) {
        const now = new Date();
        const fmt = d => d.toISOString().split('T')[0];
        let since, until;
        
        switch(preset) {
            case 'today':
                since = until = fmt(now);
                break;
            case 'yesterday':
                const yest = new Date(now); yest.setDate(yest.getDate() - 1);
                since = until = fmt(yest);
                break;
            case 'this_week':
                const mon = new Date(now); mon.setDate(mon.getDate() - mon.getDay() + 1);
                if (mon > now) mon.setDate(mon.getDate() - 7);
                since = fmt(mon); until = fmt(now);
                break;
            case '7days':
                const d7 = new Date(now); d7.setDate(d7.getDate() - 7);
                since = fmt(d7); until = fmt(now);
                break;
            case '14days':
                const d14 = new Date(now); d14.setDate(d14.getDate() - 14);
                since = fmt(d14); until = fmt(now);
                break;
            case '30days':
                const d30 = new Date(now); d30.setDate(d30.getDate() - 30);
                since = fmt(d30); until = fmt(now);
                break;
            case 'this_month':
                since = fmt(new Date(now.getFullYear(), now.getMonth(), 1));
                until = fmt(now);
                break;
            case 'last_month':
                const firstLast = new Date(now.getFullYear(), now.getMonth() - 1, 1);
                const lastLast = new Date(now.getFullYear(), now.getMonth(), 0);
                since = fmt(firstLast); until = fmt(lastLast);
                break;
        }
        
        document.getElementById('since').value = since;
        document.getElementById('until').value = until;
        
        // Highlight active preset
        document.querySelectorAll('.presets button').forEach(b => b.classList.remove('active'));
        event.target.classList.add('active');
        
        // Submit form
        document.querySelector('.filters form').submit();
    }
    
    // Freeze all cost prices
    function freezeAllCosts() {
        if (!confirm('Đóng băng giá vốn vào tất cả đơn hàng? Giá vốn hiện tại sẽ được lưu vào đơn hàng và không thay đổi khi bạn cập nhật giá mới.')) {
            return;
        }
        
        fetch('/api/freeze-costs', { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                alert(`Đã đóng băng giá vốn cho ${data.updated} đơn hàng`);
                location.reload();
            })
            .catch(err => {
                alert('Lỗi: ' + err.message);
            });
    }
    
    // Show order detail modal
    function showOrderDetail(threadId, customer, date, revenue, cost, profit, items, fees) {
        document.getElementById('modal-title').innerHTML = `📦 Chi tiết đơn hàng #${threadId}`;
        
        const hasCost = cost > 0;
        const margin = hasCost && revenue > 0 ? ((profit / revenue) * 100).toFixed(1) : 0;
        
        let itemsHtml = '';
        if (items && items.length > 0) {
            itemsHtml = `
                <table style="width:100%; border-collapse:collapse; margin:10px 0;">
                    <thead>
                        <tr style="background:#f8f9fa;">
                            <th style="padding:8px; text-align:left; border-bottom:1px solid #eee;">Mã SP</th>
                            <th style="padding:8px; text-align:right; border-bottom:1px solid #eee;">SL</th>
                            <th style="padding:8px; text-align:right; border-bottom:1px solid #eee;">Giá bán</th>
                            <th style="padding:8px; text-align:right; border-bottom:1px solid #eee;">Giá vốn</th>
                            <th style="padding:8px; text-align:right; border-bottom:1px solid #eee;">Doanh thu</th>
                            <th style="padding:8px; text-align:right; border-bottom:1px solid #eee;">Chi phí</th>
                            <th style="padding:8px; text-align:right; border-bottom:1px solid #eee;">Lợi nhuận</th>
                            <th style="padding:8px; text-align:right; border-bottom:1px solid #eee;">%LN</th>
                        </tr>
                    </thead>
                    <tbody>`;
            
            items.forEach(item => {
                const itemRevenue = item.revenue || (item.qty * item.sell_price);
                const itemCost = item.cost || (item.qty * item.cost_price);
                const itemProfit = item.profit || (item.has_cost ? itemRevenue - itemCost : 0);
                const itemMargin = item.has_cost && itemRevenue > 0 ? ((itemProfit / itemRevenue) * 100).toFixed(1) : 0;
                const profitClass = itemProfit > 0 ? 'color:#22c55e' : (itemProfit < 0 ? 'color:#ef4444' : '');
                
                itemsHtml += `
                    <tr>
                        <td style="padding:8px; border-bottom:1px solid #eee;"><strong>${item.code}</strong></td>
                        <td style="padding:8px; text-align:right; border-bottom:1px solid #eee;">${item.qty}</td>
                        <td style="padding:8px; text-align:right; border-bottom:1px solid #eee;">${(item.sell_price || 0).toLocaleString()}đ</td>
                        <td style="padding:8px; text-align:right; border-bottom:1px solid #eee;">${item.has_cost ? (item.cost_price || 0).toLocaleString() + 'đ' : '<span style="color:#f59e0b">?</span>'}</td>
                        <td style="padding:8px; text-align:right; border-bottom:1px solid #eee;">${itemRevenue.toLocaleString()}đ</td>
                        <td style="padding:8px; text-align:right; border-bottom:1px solid #eee;">${item.has_cost ? itemCost.toLocaleString() + 'đ' : '-'}</td>
                        <td style="padding:8px; text-align:right; border-bottom:1px solid #eee; ${profitClass}">${item.has_cost ? itemProfit.toLocaleString() + 'đ' : '<span style="color:#f59e0b">0đ</span>'}</td>
                        <td style="padding:8px; text-align:right; border-bottom:1px solid #eee; ${profitClass}">${item.has_cost ? itemMargin + '%' : '-'}</td>
                    </tr>`;
            });
            
            itemsHtml += '</tbody></table>';
        }
        
        const profitColor = profit > 0 ? '#22c55e' : (profit < 0 ? '#ef4444' : '#333');
        
        // Build fee display if any fees exist
        let feesHtml = '';
        if (fees && (fees.vat || fees.pvc || fees.discount)) {
            feesHtml = '<div style="margin-top:12px; padding:12px; background:#fffbe6; border-radius:8px; font-size:13px;">';
            feesHtml += '<strong>📊 Phí & Thuế:</strong> ';
            if (fees.vat) feesHtml += `<span style="margin-left:8px;">VAT: +${fees.vat.toLocaleString()}đ</span>`;
            if (fees.pvc) feesHtml += `<span style="margin-left:8px;">Ship: +${fees.pvc.toLocaleString()}đ</span>`;
            if (fees.discount) feesHtml += `<span style="margin-left:8px;">Giảm: -${fees.discount.toLocaleString()}đ</span>`;
            feesHtml += '<br><span style="color:#666;">Đã cộng vào doanh thu và lợi nhuận</span>';
            feesHtml += '</div>';
        }
        
        document.getElementById('modal-content').innerHTML = `
            <div style="margin-bottom:20px;">
                <p><strong>Khách hàng:</strong> ${customer || 'N/A'}</p>
                <p><strong>Ngày:</strong> ${date || 'N/A'}</p>
                <p><a href="tg://privatepost?channel=2124542200&post=${threadId}" target="_blank">Mở trong Telegram →</a></p>
            </div>
            
            <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:10px; margin-bottom:20px;">
                <div style="background:#f8f9fa; padding:15px; border-radius:8px; text-align:center;">
                    <div style="font-size:12px; color:#666;">Doanh thu</div>
                    <div style="font-size:18px; font-weight:bold;">${revenue.toLocaleString()}đ</div>
                </div>
                <div style="background:#f8f9fa; padding:15px; border-radius:8px; text-align:center;">
                    <div style="font-size:12px; color:#666;">Giá vốn</div>
                    <div style="font-size:18px; font-weight:bold;">${hasCost ? cost.toLocaleString() + 'đ' : '?'}</div>
                </div>
                <div style="background:#f8f9fa; padding:15px; border-radius:8px; text-align:center;">
                    <div style="font-size:12px; color:#666;">Lợi nhuận</div>
                    <div style="font-size:18px; font-weight:bold; color:${profitColor};">${hasCost ? profit.toLocaleString() + 'đ' : '?'}</div>
                </div>
                <div style="background:#f8f9fa; padding:15px; border-radius:8px; text-align:center;">
                    <div style="font-size:12px; color:#666;">Biên LN</div>
                    <div style="font-size:18px; font-weight:bold; color:${profitColor};">${hasCost ? margin + '%' : '?'}</div>
                </div>
            </div>
            
            <h3 style="margin:15px 0 10px;">Chi tiết sản phẩm</h3>
            ${feesHtml}
            ${itemsHtml}
        `;
        
        document.getElementById('orderModal').style.display = 'block';
    }
    
    function closeModal() {
        document.getElementById('orderModal').style.display = 'none';
    }
    
    // Close modal on outside click
    document.addEventListener('DOMContentLoaded', function() {
        const modal = document.getElementById('orderModal');
        if (modal) {
            modal.addEventListener('click', function(e) {
                if (e.target === this) closeModal();
            });
        }
    });
    
    // Infinite scroll for orders
    let currentPage = 1;
    let isLoading = false;
    let hasMore = true;
    
    function loadMoreOrders() {
        if (isLoading || !hasMore) return;
        
        isLoading = true;
        document.getElementById('loading-row').style.display = 'table-row';
        
        currentPage++;
        const params = new URLSearchParams(window.location.search);
        params.set('page', currentPage);
        
        fetch(`/api/orders?${params.toString()}`)
            .then(r => r.json())
            .then(data => {
                if (data.orders.length === 0) {
                    hasMore = false;
                    document.getElementById('loading-row').style.display = 'none';
                    return;
                }
                
                const tbody = document.querySelector('#orders-tab tbody');
                const loadingRow = document.getElementById('loading-row');
                
                data.orders.forEach(od => {
                    const profitClass = od.profit > 0 ? 'positive' : (od.profit < 0 ? 'negative' : '');
                    const profitDisplay = od.has_cost ? `${od.revenue - od.cost}đ` : '<span class="tag yellow">Chưa có giá vốn</span>';
                    
                    // Build product details
                    let productsHtml = '-';
                    if (od.items && od.items.length > 0) {
                        productsHtml = od.items.map(item => {
                            if (item.has_cost) {
                                return `${item.code}(${item.qty})`;
                            } else {
                                return `<span style='color:#f59e0b'>${item.code}(${item.qty})</span>`;
                            }
                        }).join('<br>');
                    }
                    
                    const row = document.createElement('tr');
                    row.style.cursor = 'pointer';
                    row.innerHTML = `
                        <td><a href="tg://privatepost?channel=2124542200&post=${od.thread_id}" target="_blank" onclick="event.stopPropagation()">#${od.thread_id}</a></td>
                        <td>${od.date}</td>
                        <td>${od.customer}</td>
                        <td style="font-size: 12px;">${productsHtml}</td>
                        <td>${od.revenue.toLocaleString()}đ</td>
                        <td>${od.cost.toLocaleString()}đ</td>
                        <td class="profit ${profitClass}">${profitDisplay}</td>
                        <td>${od.revenue > 0 && od.has_cost ? ((od.profit / od.revenue) * 100).toFixed(1) + '%' : '0%'}</td>
                    `;
                    row.addEventListener('click', function() {
                        showOrderDetail(od.thread_id, od.customer, od.date, od.revenue, od.cost, od.profit, od.items, od.fees || {});
                    });
                    tbody.insertBefore(row, loadingRow);
                });
                
                hasMore = data.has_more;
                isLoading = false;
                document.getElementById('loading-row').style.display = 'none';
            })
            .catch(err => {
                console.error('Error loading orders:', err);
                isLoading = false;
                document.getElementById('loading-row').style.display = 'none';
            });
    }
    
    // Detect scroll to bottom
    window.addEventListener('scroll', () => {
        if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 500) {
            loadMoreOrders();
        }
    });
    </script>
</body>
</html>"""
    
    # Replace chart data placeholder
    html = html.replace('__CHART_DATA__', chart_data)
    return html


def generate_product_detail_html(db_conn, product_code, since_date=None, until_date=None):
    """Generate detail page for a specific product."""
    product = get_product(db_conn, product_code)
    
    # If product not in table, create a placeholder
    if not product:
        product = {
            "code": product_code,
            "name": "",
            "cost_price": 0,
            "note": "Chưa có giá vốn",
            "created_at": None,
            "updated_at": None,
        }
    
    # Get orders containing this product (from May 2026 onwards)
    cur = db_conn.execute(
        "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL "
        "AND json IS NOT NULL AND thread_id BETWEEN 460000 AND 480000 "
        "ORDER BY thread_id DESC LIMIT 1000"
    )
    
    if since_date is None:
        since_date = "2026-05-01"
    
    orders_with_product = []
    total_qty = 0
    total_revenue = 0
    total_cost = 0
    total_profit = 0
    
    for row in cur.fetchall():
        thread_id = row[0]
        order = json.loads(row[1])
        
        # Filter by date range (VN timezone UTC+7)
        created = order.get("created", "")
        if created:
            try:
                vn_tz = timezone(timedelta(hours=7))
                if isinstance(created, str):
                    dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                elif created > 1e10:
                    dt = datetime.fromtimestamp(created / 1000, tz=timezone.utc)
                else:
                    dt = datetime.fromtimestamp(created, tz=timezone.utc)
                created_date = dt.astimezone(vn_tz).strftime("%Y-%m-%d")
                if since_date and created_date < since_date:
                    continue
                if until_date and created_date > until_date:
                    continue
            except:
                continue
        
        invoice = order.get("invoice") or order.get("invoice_items") or []
        for item in invoice:
            if (item.get("sp") or "").upper().strip() == product_code:
                qty = int(item.get("sl", 0))
                sell_price = int(item.get("price", 0))
                revenue = qty * sell_price
                
                # Use frozen cost_price from invoice item if available
                frozen_cost = item.get("cost_price")
                if frozen_cost is not None:
                    cost_price = int(frozen_cost)
                else:
                    cost_price = product.get("cost_price", 0)
                
                cost = qty * cost_price
                profit = (revenue - cost) if cost_price > 0 else 0
                
                customer = order.get("customer_name") or order.get("khach_hang") or ""
                # Extract name if customer is a dict
                if isinstance(customer, dict):
                    customer = customer.get("name", "")
                customer = str(customer or "")
                
                orders_with_product.append({
                    "thread_id": thread_id,
                    "customer": customer,
                    "qty": qty,
                    "sell_price": sell_price,
                    "revenue": revenue,
                    "cost": cost,
                    "profit": profit,
                    "created": order.get("created", ""),
                })
                
                total_qty += qty
                total_revenue += revenue
                total_cost += cost
                # If cost is 0, profit is 0
                total_profit += profit if cost_price > 0 else 0
    
    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chi tiết sản phẩm {product_code}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 10px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #333; margin-bottom: 16px; font-size: 20px; }}
        .back {{ color: #3b82f6; text-decoration: none; margin-bottom: 16px; display: inline-block; }}
        .nav {{ margin-bottom: 16px; display: flex; flex-wrap: wrap; gap: 6px; }}
        .nav a {{ padding: 8px 12px; background: #3b82f6; color: white; text-decoration: none; border-radius: 5px; white-space: nowrap; font-size: 13px; }}
        .nav a:hover {{ background: #2563eb; }}
        .product-info {{ background: white; border-radius: 10px; padding: 16px; margin-bottom: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 16px; }}
        .card {{ background: white; border-radius: 10px; padding: 14px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; }}
        .card h3 {{ color: #666; font-size: 11px; margin-bottom: 4px; }}
        .card .value {{ font-size: 18px; font-weight: bold; }}
        .card .value.positive {{ color: #22c55e; }}
        .card .value.negative {{ color: #ef4444; }}
        .table-wrap {{ width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; background: white; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        table {{ width: 100%; min-width: 600px; border-collapse: collapse; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; font-size: 14px; }}
        th {{ background: #f8f9fa; font-weight: 600; color: #333; white-space: nowrap; }}
        tr:hover {{ background: #f5f5f5; }}
        .profit {{ font-weight: 600; }}
        .profit.positive {{ color: #22c55e; }}
        .profit.negative {{ color: #ef4444; }}
        .form {{ background: white; border-radius: 10px; padding: 16px; margin-bottom: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }}
        .form input, .form button {{ padding: 8px 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 13px; }}
        .form button {{ background: #3b82f6; color: white; cursor: pointer; border: none; }}
        .form button:hover {{ background: #2563eb; }}
        @media (max-width: 768px) {{
            body {{ padding: 8px; }}
            h1 {{ font-size: 18px; }}
            .summary {{ grid-template-columns: 1fr 1fr; gap: 8px; }}
            .nav a {{ font-size: 12px; padding: 6px 10px; }}
            .form {{ flex-direction: column; align-items: stretch; }}
            th, td {{ padding: 8px 10px; font-size: 13px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/">🏠 Dashboard</a>
            <a href="/customers">👥 Khách hàng</a>
        </div>
        <h1>📦 Sản phẩm: {product_code}</h1>
        
        <div class="filter-bar">
            {_get_date_presets_html()}
            <form method="GET" action="/product/{product_code}" style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; width: 100%;">
                <input type="date" name="since" value="{since_date or '2026-05-01'}" title="Từ ngày" onchange="this.form.submit()">
                <input type="date" name="until" value="{until_date or ''}" title="Đến ngày" onchange="this.form.submit()">
                <button type="submit">🔍 Lọc</button>
                <a href="/product/{product_code}" style="padding: 8px 12px; text-decoration: none; color: #3b82f6;">Xóa bộ lọc</a>
            </form>
        </div>
        
        <div class="product-info">
            <form method="POST" action="/product/{product_code}/cost" class="form">
                <label>Giá vốn: </label>
                <input type="number" name="cost_price" value="{product['cost_price']}" placeholder="Giá vốn">
                <button type="submit">💾 Cập nhật</button>
                {f'<span style="color: #ef4444; margin-left: 10px;">⚠️ Chưa có giá vốn - lợi nhuận sẽ = 0</span>' if product['cost_price'] == 0 else ''}
            </form>
        </div>
        
        <div class="summary">
            <div class="card">
                <h3>📦 Số lượng bán</h3>
                <div class="value">{total_qty}</div>
            </div>
            <div class="card">
                <h3>💰 Doanh thu</h3>
                <div class="value">{_format_money(total_revenue)}đ</div>
            </div>
            <div class="card">
                <h3>💵 Giá vốn</h3>
                <div class="value">{_format_money(total_cost)}đ</div>
            </div>
            <div class="card">
                <h3>📈 Lợi nhuận</h3>
                <div class="value {'positive' if total_profit >= 0 else 'negative'}">{_format_money(total_profit)}đ</div>
            </div>
        </div>
        
        <h2>📋 Đơn hàng chứa sản phẩm này</h2>
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Đơn hàng</th>
                    <th>Khách hàng</th>
                    <th>SL</th>
                    <th>Giá bán</th>
                    <th>Doanh thu</th>
                    <th>Giá vốn</th>
                    <th>Lợi nhuận</th>
                </tr>
            </thead>
            <tbody>"""
    
    for od in orders_with_product[:50]:
        profit_class = "positive" if od["profit"] >= 0 else "negative"
        cust_name = (od['customer'] or '')[:25]
        html += f"""
                <tr onclick="location.href='/order/{od['thread_id']}'" style="cursor: pointer;">
                    <td><a href="/order/{od['thread_id']}" style="color: #3b82f6; text-decoration: none;" onclick="event.stopPropagation()"><strong>#{od['thread_id']}</strong></a></td>
                    <td>{cust_name}</td>
                    <td>{od['qty']}</td>
                    <td>{_format_money(od['sell_price'])}đ</td>
                    <td>{_format_money(od['revenue'])}đ</td>
                    <td>{_format_money(od['cost'])}đ</td>
                    <td class="profit {profit_class}">{_format_money(od['profit'])}đ</td>
                </tr>"""
    
    html += """
            </tbody>
        </table>
        </div>
    </div>
    <script>
    function setDatePreset(preset) {
        const now = new Date();
        const fmt = d => d.toISOString().split('T')[0];
        let since, until;
        switch(preset) {
            case 'today': since = until = fmt(now); break;
            case 'yesterday': const yest = new Date(now); yest.setDate(yest.getDate() - 1); since = until = fmt(yest); break;
            case 'this_week': const mon = new Date(now); mon.setDate(mon.getDate() - mon.getDay() + 1); if (mon > now) mon.setDate(mon.getDate() - 7); since = fmt(mon); until = fmt(now); break;
            case '7days': const d7 = new Date(now); d7.setDate(d7.getDate() - 7); since = fmt(d7); until = fmt(now); break;
            case '14days': const d14 = new Date(now); d14.setDate(d14.getDate() - 14); since = fmt(d14); until = fmt(now); break;
            case '30days': const d30 = new Date(now); d30.setDate(d30.getDate() - 30); since = fmt(d30); until = fmt(now); break;
            case 'this_month': since = fmt(new Date(now.getFullYear(), now.getMonth(), 1)); until = fmt(now); break;
            case 'last_month': const firstLast = new Date(now.getFullYear(), now.getMonth() - 1, 1); const lastLast = new Date(now.getFullYear(), now.getMonth(), 0); since = fmt(firstLast); until = fmt(lastLast); break;
        }
        document.querySelector('input[name="since"]').value = since;
        document.querySelector('input[name="until"]').value = until;
        document.querySelector('.filter-bar form').submit();
    }
    </script>
</body>
</html>"""
    
    return html


def generate_customer_profit_html(db_conn, since_date=None, until_date=None):
    """Generate customer profit analysis page."""
    if since_date is None:
        since_date = "2026-05-01"
    
    cur = db_conn.execute(
        "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL "
        "AND json IS NOT NULL AND thread_id BETWEEN 460000 AND 480000 "
        "ORDER BY thread_id DESC LIMIT 500"
    )
    
    customer_data = {}  # customer_name -> {revenue, cost, profit, orders, products}
    
    for row in cur.fetchall():
        order = json.loads(row[1])
        created = order.get("created", "")
        
        # Filter by date range (VN timezone UTC+7)
        if created:
            try:
                vn_tz = timezone(timedelta(hours=7))
                if isinstance(created, str):
                    dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                    created_date = dt.astimezone(vn_tz).strftime("%Y-%m-%d")
                elif created > 1e10:
                    created_date = datetime.fromtimestamp(created / 1000, tz=timezone.utc).astimezone(vn_tz).strftime("%Y-%m-%d")
                else:
                    created_date = datetime.fromtimestamp(created, tz=timezone.utc).astimezone(vn_tz).strftime("%Y-%m-%d")
                if since_date and created_date < since_date:
                    continue
                if until_date and created_date > until_date:
                    continue
            except:
                continue
        
        customer = order.get("customer_name") or order.get("khach_hang") or ""
        if isinstance(customer, dict):
            customer = customer.get("name", "")
        customer = str(customer or "Khách lẻ")
        
        result = calculate_order_profit(db_conn, order)
        if not result["items"]:
            continue
        
        if customer not in customer_data:
            customer_data[customer] = {
                "revenue": 0, "cost": 0, "profit": 0, 
                "orders": 0, "products": set()
            }
        
        cd = customer_data[customer]
        cd["revenue"] += result["total_revenue"]
        cd["cost"] += result["total_cost"]
        cd["profit"] += result["total_profit"]
        cd["orders"] += 1
        for item in result["items"]:
            cd["products"].add(item["code"])
    
    # Sort by profit descending
    sorted_customers = sorted(customer_data.items(), key=lambda x: x[1]["profit"], reverse=True)
    
    total_revenue = sum(d["revenue"] for _, d in sorted_customers)
    total_cost = sum(d["cost"] for _, d in sorted_customers)
    total_profit = sum(d["profit"] for _, d in sorted_customers)
    
    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Phân tích lợi nhuận theo khách hàng</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 10px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #333; margin-bottom: 16px; font-size: 20px; }}
        .nav {{ margin-bottom: 16px; display: flex; flex-wrap: wrap; gap: 6px; }}
        .nav a {{ padding: 8px 12px; background: #3b82f6; color: white; text-decoration: none; border-radius: 5px; white-space: nowrap; font-size: 13px; }}
        .nav a:hover {{ background: #2563eb; }}
        .nav a.active {{ background: #1d4ed8; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 24px; }}
        .card {{ background: white; border-radius: 10px; padding: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; }}
        .card h3 {{ color: #666; font-size: 12px; margin-bottom: 6px; }}
        .card .value {{ font-size: 20px; font-weight: bold; }}
        .card .value.positive {{ color: #22c55e; }}
        .card .value.negative {{ color: #ef4444; }}
        .filters {{ background: white; border-radius: 10px; padding: 12px; margin-bottom: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }}
        .filters input, .filters button {{ padding: 8px 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 13px; }}
        .filters button {{ background: #3b82f6; color: white; cursor: pointer; border: none; }}
        .filters a {{ padding: 8px 10px; text-decoration: none; color: #3b82f6; white-space: nowrap; font-size: 13px; }}
        .table-wrap {{ width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; background: white; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        table {{ width: 100%; min-width: 600px; border-collapse: collapse; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; font-size: 14px; }}
        th {{ background: #f8f9fa; font-weight: 600; color: #333; white-space: nowrap; }}
        tr:hover {{ background: #f5f5f5; }}
        .profit {{ font-weight: 600; }}
        .profit.positive {{ color: #22c55e; }}
        .profit.negative {{ color: #ef4444; }}
        @media (max-width: 768px) {{
            body {{ padding: 8px; }}
            h1 {{ font-size: 18px; }}
            .summary {{ grid-template-columns: 1fr 1fr; gap: 8px; }}
            .card {{ padding: 12px; }}
            .card h3 {{ font-size: 11px; }}
            .card .value {{ font-size: 18px; }}
            .nav a {{ font-size: 12px; padding: 6px 10px; }}
            .filters {{ flex-direction: column; align-items: stretch; }}
            .filters input {{ width: 100% !important; }}
            .filters button {{ width: 100%; }}
            th, td {{ padding: 8px 10px; font-size: 13px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/">🏠 Dashboard</a>
            <a href="/customers" class="active">👥 Khách hàng</a>
            <a href="/export/orders">📥 Export CSV</a>
        </div>
        <h1>👥 Phân tích lợi nhuận theo khách hàng</h1>
        
        <div class="filters">
            <div class="presets">
                <button type="button" onclick="setDatePreset('today')">Hôm nay</button>
                <button type="button" onclick="setDatePreset('yesterday')">Hôm qua</button>
                <button type="button" onclick="setDatePreset('this_week')">Tuần này</button>
                <button type="button" onclick="setDatePreset('7days')">7 ngày</button>
                <button type="button" onclick="setDatePreset('14days')">14 ngày</button>
                <button type="button" onclick="setDatePreset('30days')">30 ngày</button>
                <button type="button" onclick="setDatePreset('this_month')">Tháng này</button>
                <button type="button" onclick="setDatePreset('last_month')">Tháng trước</button>
            </div>
            <form method="GET" action="/customers">
                <input type="date" name="since" id="since" value="{since_date or '2026-05-01'}" title="Từ ngày">
                <input type="date" name="until" id="until" value="{until_date or ''}" title="Đến ngày">
                <button type="submit">🔍 Lọc</button>
                <a href="/customers" style="padding: 8px 12px; text-decoration: none; color: #3b82f6;">Xóa bộ lọc</a>
            </form>
        </div>
        
        <div class="summary">
            <div class="card">
                <h3>👥 Tổng khách hàng</h3>
                <div class="value">{len(sorted_customers)}</div>
            </div>
            <div class="card">
                <h3>📦 Doanh thu</h3>
                <div class="value">{_format_money(total_revenue)}đ</div>
            </div>
            <div class="card">
                <h3>💵 Giá vốn</h3>
                <div class="value">{_format_money(total_cost)}đ</div>
            </div>
            <div class="card">
                <h3>💰 Lợi nhuận</h3>
                <div class="value {'positive' if total_profit >= 0 else 'negative'}">{_format_money(total_profit)}đ</div>
            </div>
        </div>
        
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Khách hàng</th>
                    <th>Đơn hàng</th>
                    <th>Sản phẩm</th>
                    <th>Doanh thu</th>
                    <th>Giá vốn</th>
                    <th>Lợi nhuận</th>
                    <th>Biên LN</th>
                </tr>
            </thead>
            <tbody>"""
    
    for customer, data in sorted_customers[:100]:
        profit_class = "positive" if data["profit"] > 0 else ("negative" if data["profit"] < 0 else "")
        margin = (data["profit"] / data["revenue"] * 100) if data["revenue"] > 0 else 0
        has_cost = data["cost"] > 0
        profit_display = f'{_format_money(data["profit"])}đ' if has_cost else 'N/A'
        
        html += f"""
                <tr>
                    <td><strong>{customer[:40]}</strong></td>
                    <td>{data['orders']}</td>
                    <td>{len(data['products'])}</td>
                    <td>{_format_money(data['revenue'])}đ</td>
                    <td>{_format_money(data['cost'])}đ</td>
                    <td class="profit {profit_class}">{profit_display}</td>
                    <td>{margin:.1f}%</td>
                </tr>"""
    
    html += """
            </tbody>
        </table>
        </div>
    </div>
    <script>
    function setDatePreset(preset) {
        const now = new Date();
        const fmt = d => d.toISOString().split('T')[0];
        let since, until;
        switch(preset) {
            case 'today': since = until = fmt(now); break;
            case 'yesterday': const yest = new Date(now); yest.setDate(yest.getDate() - 1); since = until = fmt(yest); break;
            case 'this_week': const mon = new Date(now); mon.setDate(mon.getDate() - mon.getDay() + 1); if (mon > now) mon.setDate(mon.getDate() - 7); since = fmt(mon); until = fmt(now); break;
            case '7days': const d7 = new Date(now); d7.setDate(d7.getDate() - 7); since = fmt(d7); until = fmt(now); break;
            case '14days': const d14 = new Date(now); d14.setDate(d14.getDate() - 14); since = fmt(d14); until = fmt(now); break;
            case '30days': const d30 = new Date(now); d30.setDate(d30.getDate() - 30); since = fmt(d30); until = fmt(now); break;
            case 'this_month': since = fmt(new Date(now.getFullYear(), now.getMonth(), 1)); until = fmt(now); break;
            case 'last_month': const fl = new Date(now.getFullYear(), now.getMonth() - 1, 1); const ll = new Date(now.getFullYear(), now.getMonth(), 0); since = fmt(fl); until = fmt(ll); break;
        }
        document.getElementById('since').value = since;
        document.getElementById('until').value = until;
        document.querySelectorAll('.presets button').forEach(b => b.classList.remove('active'));
        event.target.classList.add('active');
        document.querySelector('.filters form').submit();
    }
    </script>
</body>
</html>"""
    
    return html


def generate_customer_detail_html(db_conn, customer_name, filter_product=None, since_date=None, until_date=None, limit=500):
    """Generate customer detail page with all orders."""
    vn_tz = timezone(timedelta(hours=7))
    
    # Default date range
    if since_date is None:
        since_date = "2026-05-01"
    
    # Get all orders
    cur = db_conn.execute(
        "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL "
        "AND json IS NOT NULL AND thread_id BETWEEN 460000 AND 480000 "
        "ORDER BY thread_id DESC LIMIT ?",
        (limit * 3,)  # Get more to account for filtering
    )
    
    customer_orders = []
    total_revenue = 0
    total_cost = 0
    total_profit = 0
    products_bought = {}  # code -> {qty, revenue, profit}
    
    for row in cur.fetchall():
        thread_id = row[0]
        order = json.loads(row[1])
        
        # Get customer name
        customer = order.get("customer_name") or order.get("khach_hang") or ""
        if isinstance(customer, dict):
            customer = customer.get("name", "")
        customer = str(customer or "").strip() or "Khách lẻ"
        
        # Match customer (case-insensitive)
        if customer.lower() != customer_name.lower():
            continue
        
        # Filter by date
        created = order.get("created", "")
        if created:
            try:
                if isinstance(created, str):
                    dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                elif created > 1e10:
                    dt = datetime.fromtimestamp(created / 1000, tz=timezone.utc)
                else:
                    dt = datetime.fromtimestamp(created, tz=timezone.utc)
                created_date = dt.astimezone(vn_tz).strftime("%Y-%m-%d")
                if since_date and created_date < since_date:
                    continue
                if until_date and created_date > until_date:
                    continue
            except:
                continue
        
        result = calculate_order_profit(db_conn, order)
        if not result["items"]:
            continue
        
        # Filter by product if specified
        if filter_product:
            has_product = any(item["code"] == filter_product for item in result["items"])
            if not has_product:
                continue
        
        # Format date
        try:
            if isinstance(created, str):
                dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
            elif created > 1e10:
                dt = datetime.fromtimestamp(created / 1000, tz=timezone.utc)
            else:
                dt = datetime.fromtimestamp(created, tz=timezone.utc)
            vn = dt.astimezone(vn_tz)
            date_display = vn.strftime("%d/%m/%Y %H:%M")
        except:
            date_display = ""
        
        customer_orders.append({
            "thread_id": thread_id,
            "created": created,
            "date_display": date_display,
            "revenue": result["total_revenue"],
            "cost": result["total_cost"],
            "profit": result["total_profit"],
            "items": result["items"],
            "item_count": result["item_count"],
            "items_with_cost": result["items_with_cost"],
        })
        
        total_revenue += result["total_revenue"]
        total_cost += result["total_cost"]
        total_profit += result["total_profit"]
        
        # Track products
        for item in result["items"]:
            code = item["code"]
            if code not in products_bought:
                products_bought[code] = {"qty": 0, "revenue": 0, "profit": 0}
            products_bought[code]["qty"] += item["qty"]
            products_bought[code]["revenue"] += item["revenue"]
            products_bought[code]["profit"] += item["profit"]
    
    # Sort orders by newest first
    customer_orders.sort(key=lambda x: x["thread_id"], reverse=True)
    
    # Sort products by profit
    top_products = sorted(products_bought.items(), key=lambda x: x[1]["profit"], reverse=True)[:10]
    
    # Calculate stats
    avg_order_value = total_revenue // len(customer_orders) if customer_orders else 0
    profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
    
    # URL encode customer name
    from urllib.parse import quote
    customer_encoded = quote(customer_name)
    
    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Khách hàng: {customer_name}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 10px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #333; margin-bottom: 8px; font-size: 22px; }}
        .subtitle {{ color: #666; font-size: 14px; margin-bottom: 16px; }}
        .nav {{ margin-bottom: 16px; display: flex; flex-wrap: wrap; gap: 6px; }}
        .nav a {{ padding: 8px 12px; background: #3b82f6; color: white; text-decoration: none; border-radius: 5px; white-space: nowrap; font-size: 13px; }}
        .nav a:hover {{ background: #2563eb; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 24px; }}
        .card {{ background: white; border-radius: 10px; padding: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; }}
        .card h3 {{ color: #666; font-size: 12px; margin-bottom: 6px; }}
        .card .value {{ font-size: 20px; font-weight: bold; }}
        .card .value.positive {{ color: #22c55e; }}
        .card .value.negative {{ color: #ef4444; }}
        .section {{ margin-bottom: 24px; }}
        .section h2 {{ color: #333; margin-bottom: 12px; font-size: 16px; }}
        .table-wrap {{ width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; background: white; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        table {{ width: 100%; min-width: 600px; border-collapse: collapse; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; font-size: 14px; }}
        th {{ background: #f8f9fa; font-weight: 600; color: #333; white-space: nowrap; }}
        tr:hover {{ background: #f5f5f5; }}
        .profit {{ font-weight: 600; }}
        .profit.positive {{ color: #22c55e; }}
        .profit.negative {{ color: #ef4444; }}
        .items-summary {{ font-size: 12px; color: #666; }}
        .filter-bar {{ background: white; border-radius: 10px; padding: 12px; margin-bottom: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
        .filter-bar input, .filter-bar button {{ padding: 8px 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 13px; }}
        .filter-bar button {{ background: #3b82f6; color: white; cursor: pointer; border: none; }}
        .filter-bar button:hover {{ background: #2563eb; }}
        .empty-state {{ text-align: center; padding: 40px; color: #999; font-size: 14px; }}
        @media (max-width: 768px) {{
            .summary {{ grid-template-columns: 1fr 1fr; gap: 8px; }}
            h1 {{ font-size: 18px; }}
            .card {{ padding: 12px; }}
            .card .value {{ font-size: 18px; }}
            th, td {{ padding: 8px 10px; font-size: 13px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/">🏠 Dashboard</a>
            <a href="/customers">👥 Khách hàng</a>
        </div>
        <h1>👤 {customer_name}</h1>
        <div class="subtitle">Chi tiết đơn hàng và lịch sử mua hàng</div>
        
        <div class="filter-bar">
            {_get_date_presets_html()}
            <form method="GET" action="/customer/{customer_encoded}" style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; width: 100%;">
                <input type="date" name="since" value="{since_date or '2026-05-01'}" title="Từ ngày" onchange="this.form.submit()">
                <input type="date" name="until" value="{until_date or ''}" title="Đến ngày" onchange="this.form.submit()">
                <input type="text" name="product" placeholder="Lọc theo mã SP" value="{filter_product or ''}">
                <button type="submit">🔍 Lọc</button>
                <a href="/customer/{customer_encoded}" style="padding: 8px 12px; text-decoration: none; color: #3b82f6;">Xóa bộ lọc</a>
            </form>
        </div>
        
        <div class="summary">
            <div class="card">
                <h3>📋 Tổng đơn</h3>
                <div class="value">{len(customer_orders)}</div>
            </div>
            <div class="card">
                <h3>📦 Doanh thu</h3>
                <div class="value">{_format_money(total_revenue)}đ</div>
            </div>
            <div class="card">
                <h3>💵 Giá vốn</h3>
                <div class="value">{_format_money(total_cost)}đ</div>
            </div>
            <div class="card">
                <h3>💰 Lợi nhuận</h3>
                <div class="value {'positive' if total_profit >= 0 else 'negative'}">{_format_money(total_profit)}đ</div>
            </div>
            <div class="card">
                <h3>📊 TB/đơn</h3>
                <div class="value">{_format_money(avg_order_value)}đ</div>
            </div>
            <div class="card">
                <h3>📈 Biên LN</h3>
                <div class="value {'positive' if profit_margin >= 0 else 'negative'}">{profit_margin:.1f}%</div>
            </div>
        </div>
        
        <div class="section">
            <h2>🛒 Sản phẩm đã mua</h2>
            <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>Mã SP</th>
                        <th>SL mua</th>
                        <th>Doanh thu</th>
                        <th>Lợi nhuận</th>
                        <th>Biên LN</th>
                    </tr>
                </thead>
                <tbody>"""
    
    if top_products:
        for code, pdata in top_products:
            margin = (pdata["profit"] / pdata["revenue"] * 100) if pdata["revenue"] > 0 else 0
            profit_class = "positive" if pdata["profit"] >= 0 else "negative"
            html += f"""
                    <tr>
                        <td><a href="/product/{code}" style="color: #3b82f6; text-decoration: none;"><strong>{code}</strong></a></td>
                        <td>{pdata['qty']}</td>
                        <td>{_format_money(pdata['revenue'])}đ</td>
                        <td class="profit {profit_class}">{_format_money(pdata['profit'])}đ</td>
                        <td>{margin:.1f}%</td>
                    </tr>"""
    else:
        html += """
                    <tr><td colspan="5" class="empty-state">Chưa có dữ liệu sản phẩm</td></tr>"""
    
    html += """
                </tbody>
            </table>
            </div>
        </div>
        
        <div class="section">
            <h2>📋 Lịch sử đơn hàng</h2>
            <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>Đơn hàng</th>
                        <th>Ngày</th>
                        <th>Sản phẩm</th>
                        <th>Doanh thu</th>
                        <th>Giá vốn</th>
                        <th>Lợi nhuận</th>
                    </tr>
                </thead>
                <tbody>"""
    
    if customer_orders:
        for od in customer_orders[:200]:  # Limit to 200 orders for performance
            profit_class = "positive" if od["profit"] >= 0 else "negative"
            has_cost = od["cost"] > 0
            profit_display = f'{_format_money(od["profit"])}đ' if has_cost else '<span style="color: #f59e0b;">Chưa có giá vốn</span>'
            
            # Build product details
            items = od.get('items', [])
            product_details = []
            for item in items[:5]:  # Show max 5 items
                code = item.get('code', '?')
                qty = item.get('qty', 0)
                product_details.append(f"{code}({qty})")
            if len(items) > 5:
                product_details.append(f"<span style='color: #999;'>+{len(items) - 5} SP khác</span>")
            products_html = "<br>".join(product_details) if product_details else "-"
            
            html += f"""
                    <tr onclick="location.href='/order/{od['thread_id']}'" style="cursor: pointer;">
                        <td><a href="/order/{od['thread_id']}" style="color: #3b82f6; text-decoration: none;" onclick="event.stopPropagation()"><strong>#{od['thread_id']}</strong></a> <a href="tg://privatepost?channel=2124542200&post={od['thread_id']}" target="_blank" onclick="event.stopPropagation()" style="color: #999; font-size: 11px;">📱</a></td>
                        <td>{od['date_display']}</td>
                        <td class="items-summary">{products_html}</td>
                        <td>{_format_money(od['revenue'])}đ</td>
                        <td>{_format_money(od['cost'])}đ</td>
                        <td class="profit {profit_class}">{profit_display}</td>
                    </tr>"""
    else:
        html += """
                    <tr><td colspan="6" class="empty-state">Chưa có đơn hàng nào trong kỳ này</td></tr>"""
    
    html += """
                </tbody>
            </table>
            </div>
        </div>
    </div>
    <script>
    function setDatePreset(preset) {
        const now = new Date();
        const fmt = d => d.toISOString().split('T')[0];
        let since, until;
        switch(preset) {
            case 'today': since = until = fmt(now); break;
            case 'yesterday': const yest = new Date(now); yest.setDate(yest.getDate() - 1); since = until = fmt(yest); break;
            case 'this_week': const mon = new Date(now); mon.setDate(mon.getDate() - mon.getDay() + 1); if (mon > now) mon.setDate(mon.getDate() - 7); since = fmt(mon); until = fmt(now); break;
            case '7days': const d7 = new Date(now); d7.setDate(d7.getDate() - 7); since = fmt(d7); until = fmt(now); break;
            case '14days': const d14 = new Date(now); d14.setDate(d14.getDate() - 14); since = fmt(d14); until = fmt(now); break;
            case '30days': const d30 = new Date(now); d30.setDate(d30.getDate() - 30); since = fmt(d30); until = fmt(now); break;
            case 'this_month': since = fmt(new Date(now.getFullYear(), now.getMonth(), 1)); until = fmt(now); break;
            case 'last_month': const firstLast = new Date(now.getFullYear(), now.getMonth() - 1, 1); const lastLast = new Date(now.getFullYear(), now.getMonth(), 0); since = fmt(firstLast); until = fmt(lastLast); break;
        }
        document.querySelector('input[name="since"]').value = since;
        document.querySelector('input[name="until"]').value = until;
        document.querySelector('.filter-bar form').submit();
    }
    </script>
</body>
</html>"""
    
    return html


def generate_order_detail_html(db_conn, thread_id):
    """Generate order detail page."""
    from order_db import get_order_by_thread_id
    
    order = get_order_by_thread_id(db_conn, thread_id)
    if not order:
        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Không tìm thấy</title></head>
<body style="font-family: sans-serif; padding: 20px;">
<h1>❌ Không tìm thấy đơn hàng #{thread_id}</h1>
<p><a href="/">← Quay lại Dashboard</a></p>
</body></html>"""
    
    vn_tz = timezone(timedelta(hours=7))
    
    # Get customer
    customer = order.get("customer_name") or order.get("khach_hang") or ""
    if isinstance(customer, dict):
        customer = customer.get("name", "")
    customer = str(customer or "").strip() or "Khách lẻ"
    
    # Format date
    created = order.get("created", "")
    date_display = ""
    if created:
        try:
            if isinstance(created, str):
                dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
            elif created > 1e10:
                dt = datetime.fromtimestamp(created / 1000, tz=timezone.utc)
            else:
                dt = datetime.fromtimestamp(created, tz=timezone.utc)
            vn = dt.astimezone(vn_tz)
            date_display = vn.strftime("%d/%m/%Y %H:%M:%S")
        except:
            date_display = ""
    
    # Calculate profit
    result = calculate_order_profit(db_conn, order)
    total_revenue = result["total_revenue"]
    total_cost = result["total_cost"]
    total_profit = result["total_profit"]
    items = result["items"]
    
    # Get fees
    vat = int(order.get("vat", 0))
    pvc = int(order.get("pvc", 0))
    discount = int(order.get("discount", 0))
    
    # Get additional fees
    extra_fees = order.get("extra_fees", [])
    fee_adjustments = order.get("fee_adjustments", [])
    
    # Process task status
    task_status = order.get("task_status", {})
    task_names = {
        "ban_hd": ("📝", "Bán hóa đơn"),
        "soan_hang": ("📦", "Soạn hàng"),
        "giao_hang": ("🚚", "Giao hàng"),
        "nop_tien": ("💵", "Nộp tiền"),
        "nhan_tien": ("💰", "Nhận tiền"),
    }
    
    tasks_html = ""
    for key, (icon, name) in task_names.items():
        task = task_status.get(key, {})
        done = task.get("done", False) or task.get("skip", False)
        skip = task.get("skip", False)
        by_id = task.get("by")
        by_name = USER_NAMES.get(str(by_id), f"User {by_id}") if by_id else "N/A"
        at_time = task.get("at", "")
        
        # Format time
        time_display = ""
        if at_time:
            try:
                if isinstance(at_time, str):
                    dt = datetime.fromisoformat(at_time.replace('Z', '+00:00'))
                elif at_time > 1e10:
                    dt = datetime.fromtimestamp(at_time / 1000, tz=timezone.utc)
                else:
                    dt = datetime.fromtimestamp(at_time, tz=timezone.utc)
                vn = dt.astimezone(vn_tz)
                time_display = vn.strftime("%d/%m/%Y %H:%M:%S")
            except:
                time_display = at_time
        
        if done:
            if skip:
                status_class = "task-skip"
                status_icon = "⏭️"
                status_text = "Bỏ qua"
            else:
                status_class = "task-done"
                status_icon = "✅"
                status_text = "Hoàn thành"
        else:
            status_class = "task-pending"
            status_icon = "⏳"
            status_text = "Chưa hoàn thành"
        
        tasks_html += f"""
            <div class="task-item {status_class}">
                <div class="task-icon">{icon}</div>
                <div class="task-content">
                    <div class="task-name">{name} {status_icon}</div>
                    <div class="task-details">
                        <span class="task-by">👤 {by_name}</span>
                        {f'<span class="task-time">🕐 {time_display}</span>' if time_display else ''}
                    </div>
                </div>
            </div>"""
    
    # Calculate margin
    margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
    
    # Back URL - try to determine where to go back
    back_url = f"/customer/{quote(customer)}" if customer != "Khách lẻ" else "/"
    
    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Đơn hàng #{thread_id}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 10px; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        h1 {{ color: #333; margin-bottom: 8px; font-size: 22px; }}
        .subtitle {{ color: #666; font-size: 14px; margin-bottom: 16px; }}
        .nav {{ margin-bottom: 16px; display: flex; flex-wrap: wrap; gap: 6px; }}
        .nav a {{ padding: 8px 12px; background: #3b82f6; color: white; text-decoration: none; border-radius: 5px; white-space: nowrap; font-size: 13px; }}
        .nav a:hover {{ background: #2563eb; }}
        .info-card {{ background: white; border-radius: 10px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 16px; }}
        .info-row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f0f0f0; }}
        .info-row:last-child {{ border-bottom: none; }}
        .info-label {{ color: #666; font-weight: 500; }}
        .info-value {{ color: #333; font-weight: 600; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 16px; }}
        .card {{ background: white; border-radius: 10px; padding: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; }}
        .card h3 {{ color: #666; font-size: 12px; margin-bottom: 6px; }}
        .card .value {{ font-size: 20px; font-weight: bold; }}
        .card .value.positive {{ color: #22c55e; }}
        .card .value.negative {{ color: #ef4444; }}
        .table-wrap {{ width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; background: white; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 16px; }}
        table {{ width: 100%; min-width: 600px; border-collapse: collapse; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; font-size: 14px; }}
        th {{ background: #f8f9fa; font-weight: 600; color: #333; white-space: nowrap; }}
        tr:hover {{ background: #f5f5f5; }}
        .profit {{ font-weight: 600; }}
        .profit.positive {{ color: #22c55e; }}
        .profit.negative {{ color: #ef4444; }}
        .text-right {{ text-align: right; }}
        .fees-section {{ background: #fffbe6; border-left: 4px solid #f59e0b; padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; }}
        .fees-section h3 {{ color: #854d0e; margin-bottom: 8px; font-size: 14px; }}
        .fees-row {{ display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; }}
        
        /* Task Timeline */
        .tasks-section {{ background: white; border-radius: 10px; padding: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 16px; }}
        .tasks-section h3 {{ color: #333; margin-bottom: 12px; font-size: 15px; }}
        .task-item {{ display: flex; align-items: center; gap: 12px; padding: 10px; border-radius: 8px; margin-bottom: 6px; transition: all 0.2s; }}
        .task-item:hover {{ background: #f8f9fa; }}
        .task-item.task-done {{ background: #f0fdf4; border-left: 3px solid #22c55e; }}
        .task-item.task-skip {{ background: #f5f5f5; border-left: 3px solid #999; opacity: 0.7; }}
        .task-item.task-pending {{ background: #fffbeb; border-left: 3px solid #f59e0b; }}
        .task-icon {{ font-size: 20px; width: 32px; text-align: center; }}
        .task-content {{ flex: 1; }}
        .task-name {{ font-weight: 600; color: #333; font-size: 14px; margin-bottom: 2px; }}
        .task-details {{ display: flex; gap: 12px; font-size: 12px; color: #666; }}
        .task-by {{ font-weight: 500; }}
        .task-time {{ color: #888; }}
        @media (max-width: 768px) {{
            .info-row {{ flex-direction: column; gap: 4px; }}
            .summary {{ grid-template-columns: 1fr 1fr; }}
            h1 {{ font-size: 18px; }}
            th, td {{ padding: 8px 10px; font-size: 13px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/">🏠 Dashboard</a>
            <a href="/customers">👥 Khách hàng</a>
            {f'<a href="{back_url}">← Quay lại</a>'}
        </div>
        <h1>📦 Đơn hàng #{thread_id}</h1>
        <div class="subtitle">Chi tiết đơn hàng</div>
        
        <div class="info-card">
            <div class="info-row">
                <span class="info-label">👤 Khách hàng:</span>
                <span class="info-value">{customer if customer == "Khách lẻ" else f'<a href="/customer/{quote(customer)}" style="color: #3b82f6;">{customer}</a>'}</span>
            </div>
            <div class="info-row">
                <span class="info-label">📅 Ngày tạo:</span>
                <span class="info-value">{date_display or "N/A"}</span>
            </div>
            <div class="info-row">
                <span class="info-label">🔗 Link Telegram:</span>
                <span class="info-value"><a href="tg://privatepost?channel=2124542200&post={thread_id}" target="_blank">Mở trong Telegram →</a></span>
            </div>
        </div>
        
        <div class="summary">
            <div class="card">
                <h3>📦 Doanh thu</h3>
                <div class="value">{_format_money(total_revenue)}đ</div>
            </div>
            <div class="card">
                <h3>💵 Giá vốn</h3>
                <div class="value">{_format_money(total_cost)}đ</div>
            </div>
            <div class="card">
                <h3>💰 Lợi nhuận</h3>
                <div class="value {'positive' if total_profit >= 0 else 'negative'}">{_format_money(total_profit)}đ</div>
            </div>
            <div class="card">
                <h3>📈 Biên LN</h3>
                <div class="value {'positive' if margin >= 0 else 'negative'}">{margin:.1f}%</div>
            </div>
        </div>
        
        <div class="tasks-section">
            <h3>📋 Tiến độ đơn hàng</h3>
            {tasks_html if tasks_html else '<div style="color: #999; font-size: 13px; padding: 10px;">Chưa có thông tin tiến độ</div>'}
        </div>
        
        {f'''
        <div class="fees-section">
            <h3>💰 Phí & Chiết khấu</h3>
            {f'''
            <div class="fees-row">
                <span>📊 VAT (thuế):</span>
                <strong style="color: #dc2626;">+{_format_money(vat)}đ</strong>
            </div>''' if vat else ''}
            {f'''
            <div class="fees-row">
                <span>🚚 Phí vận chuyển:</span>
                <strong style="color: #dc2626;">+{_format_money(pvc)}đ</strong>
            </div>''' if pvc else ''}
            {f'''
            <div class="fees-row">
                <span>🏷️ Chiết khấu:</span>
                <strong style="color: #16a34a;">-{_format_money(discount)}đ</strong>
            </div>''' if discount else ''}
            {f'''
            <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #fde68a; font-size: 12px; color: #854d0e;">
                ℹ️ Các khoản phí đã được cộng vào doanh thu và lợi nhuận
            </div>''' if (vat or pvc or discount) else ''}
        </div>
        ''' if (vat or pvc or discount or extra_fees) else ''}
        
        <h2 style="margin-bottom: 12px; font-size: 16px;">🛒 Sản phẩm ({len(items)})</h2>
        <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Mã SP</th>
                    <th class="text-right">SL</th>
                    <th class="text-right">Giá bán</th>
                    <th class="text-right">Giá vốn</th>
                    <th class="text-right">Doanh thu</th>
                    <th class="text-right">Chi phí</th>
                    <th class="text-right">Lợi nhuận</th>
                    <th class="text-right">%LN</th>
                </tr>
            </thead>
            <tbody>"""
    
    if items:
        for item in items:
            has_cost = item.get("has_cost", False)
            item_revenue = item.get("revenue", 0)
            item_cost = item.get("cost", 0)
            item_profit = item.get("profit", 0)
            item_margin = (item_profit / item_revenue * 100) if item_revenue > 0 and has_cost else 0
            
            profit_display = f'{_format_money(item_profit)}đ' if has_cost else '<span style="color: #f59e0b;">?</span>'
            cost_display = f'{_format_money(item.get("cost_price", 0))}đ' if has_cost else '<span style="color: #f59e0b;">?</span>'
            
            html += f"""
                <tr>
                    <td><a href="/product/{item['code']}" style="color: #3b82f6; text-decoration: none;"><strong>{item['code']}</strong></a></td>
                    <td class="text-right">{item['qty']}</td>
                    <td class="text-right">{_format_money(item['sell_price'])}đ</td>
                    <td class="text-right">{cost_display}</td>
                    <td class="text-right">{_format_money(item_revenue)}đ</td>
                    <td class="text-right">{_format_money(item_cost)}đ</td>
                    <td class="text-right profit {'positive' if item_profit > 0 else 'negative' if item_profit < 0 else ''}">{profit_display}</td>
                    <td class="text-right">{item_margin:.1f}%</td>
                </tr>"""
    else:
        html += """
                <tr><td colspan="8" style="text-align: center; padding: 20px; color: #999;">Không có sản phẩm</td></tr>"""
    
    html += f"""
            </tbody>
        </table>
        </div>
        
        <div style="background: white; border-radius: 10px; padding: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 16px;">
            <h3 style="margin-bottom: 12px; font-size: 15px;">📊 Tổng kết</h3>
            <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #f0f0f0;">
                <span>Tổng số sản phẩm:</span>
                <strong>{sum(item['qty'] for item in items)}</strong>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #f0f0f0;">
                <span>Số mã SP khác nhau:</span>
                <strong>{len(items)}</strong>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #f0f0f0;">
                <span>Doanh thu:</span>
                <strong>{_format_money(total_revenue)}đ</strong>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #f0f0f0;">
                <span>Giá vốn:</span>
                <strong>{_format_money(total_cost)}đ</strong>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 6px 0; padding-top: 8px; margin-top: 4px; border-top: 2px solid #333;">
                <span style="font-weight: bold; font-size: 15px;">Lợi nhuận:</span>
                <strong style="color: {'#22c55e' if total_profit >= 0 else '#ef4444'}; font-size: 15px;">{_format_money(total_profit)}đ</strong>
            </div>
        </div>
    </div>
</body>
</html>"""
    
    return html


def generate_settings_html(yearly_loan, monthly_weights=None):
    """Generate settings page HTML with monthly weight configuration."""
    if monthly_weights is None:
        monthly_weights = DEFAULT_WEIGHTS
    w = {str(m): float(monthly_weights.get(str(m), 1.0)) for m in range(1, 13)}
    MONTH_NAMES = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12"]
    avg_w = sum(w.values()) / 12.0
    monthly_base = yearly_loan / 12.0

    # Build weight input rows
    weight_rows = ""
    for m in range(1, 13):
        allocated = int(monthly_base * w[str(m)] / avg_w) if avg_w > 0 else 0
        weight_rows += f"""
                <div class="weight-row">
                    <span class="weight-label">{MONTH_NAMES[m-1]}</span>
                    <input type="number" class="weight-input" data-month="{m}" value="{w[str(m)]}" min="0" step="0.1">
                    <span class="weight-amount" id="amount-{m}">{_format_money(allocated)}đ</span>
                </div>"""

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cấu hình Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 10px; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        h1 {{ color: #333; margin-bottom: 16px; font-size: 22px; }}
        h2 {{ color: #333; margin-bottom: 12px; font-size: 16px; }}
        .nav {{ margin-bottom: 16px; display: flex; flex-wrap: wrap; gap: 6px; }}
        .nav a {{ padding: 8px 12px; background: #3b82f6; color: white; text-decoration: none; border-radius: 5px; white-space: nowrap; font-size: 13px; }}
        .nav a:hover {{ background: #2563eb; }}
        .nav a.active {{ background: #1d4ed8; }}
        .settings-card {{ background: white; border-radius: 10px; padding: 24px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 16px; }}
        .form-group {{ margin-bottom: 20px; }}
        .form-group label {{ display: block; color: #333; font-weight: 600; margin-bottom: 8px; font-size: 14px; }}
        .form-group input {{ width: 100%; padding: 12px; border: 2px solid #e5e7eb; border-radius: 8px; font-size: 16px; transition: border-color 0.2s; }}
        .form-group input:focus {{ outline: none; border-color: #3b82f6; }}
        .form-group .help {{ color: #666; font-size: 12px; margin-top: 4px; }}
        .btn {{ padding: 12px 24px; background: #22c55e; color: white; border: none; border-radius: 8px; font-size: 15px; font-weight: 600; cursor: pointer; }}
        .btn:hover {{ background: #16a34a; }}
        .btn-reset {{ background: #6b7280; margin-left: 8px; }}
        .btn-reset:hover {{ background: #4b5563; }}
        .weight-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px; margin-top: 12px; }}
        .weight-row {{ display: flex; align-items: center; gap: 8px; background: #f9fafb; padding: 8px 12px; border-radius: 8px; border: 1px solid #e5e7eb; }}
        .weight-label {{ font-weight: 600; color: #374151; min-width: 32px; font-size: 14px; }}
        .weight-input {{ width: 70px !important; padding: 6px 8px !important; font-size: 14px !important; text-align: center; border: 2px solid #e5e7eb; border-radius: 6px; }}
        .weight-input:focus {{ outline: none; border-color: #3b82f6; }}
        .weight-amount {{ color: #1e40af; font-size: 13px; font-weight: 500; margin-left: auto; white-space: nowrap; }}
        .preview {{ background: #f0f9ff; border-left: 4px solid #3b82f6; padding: 16px; border-radius: 8px; margin-top: 20px; }}
        .preview h3 {{ color: #1e40af; margin-bottom: 8px; font-size: 14px; }}
        .preview-row {{ display: flex; justify-content: space-between; padding: 6px 0; font-size: 13px; }}
        .preview-row strong {{ color: #1e40af; }}
        .alert {{ padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; font-size: 14px; display: none; }}
        .alert.success {{ background: #dcfce7; color: #166534; border: 1px solid #86efac; }}
        .alert.error {{ background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }}
        @media (max-width: 768px) {{
            .settings-card {{ padding: 16px; }}
            .weight-grid {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/">🏠 Dashboard</a>
            <a href="/customers">👥 Khách hàng</a>
            <a href="/settings" class="active">⚙️ Cấu hình</a>
        </div>
        <h1>⚙️ Cấu hình Dashboard</h1>

        <div id="alert" class="alert"></div>

        <div class="settings-card">
            <form id="settingsForm">
                <div class="form-group">
                    <label for="yearly_loan">💳 Tổng lãi vay ngân hàng 1 năm (VNĐ)</label>
                    <input type="number" id="yearly_loan" name="yearly_loan" value="{yearly_loan}" placeholder="Nhập tổng số tiền lãi vay phải trả trong 1 năm" min="0" step="100000">
                    <div class="help">Tổng lãi vay 1 năm, sẽ được phân bổ theo trọng số từng tháng bên dưới.</div>
                </div>

                <h2>📊 Trọng số phân bổ theo tháng</h2>
                <div class="help" style="margin-bottom: 8px;">Mỗi tháng có một trọng số (mặc định 1.0). Tháng trọng số cao hơn sẽ chịu nhiều lãi vay hơn. Tổng phân bổ cả năm vẫn bằng tổng lãi vay bạn nhập.</div>
                <div class="weight-grid" id="weightGrid">{weight_rows}
                </div>
                <div style="margin-top: 8px; display: flex; gap: 8px;">
                    <button type="button" class="btn btn-reset" onclick="resetWeights()">↺ Reset về 1.0</button>
                    <button type="button" class="btn btn-reset" onclick="equalizeWeights()">= Chia đều</button>
                </div>

                <div class="preview">
                    <h3>📊 Xem trước</h3>
                    <div class="preview-row">
                        <span>Tổng lãi vay/năm:</span>
                        <strong id="preview-yearly">{_format_money(yearly_loan)}đ</strong>
                    </div>
                    <div class="preview-row">
                        <span>Trung bình/tháng:</span>
                        <strong id="preview-monthly">{_format_money(int(yearly_loan / 12))}đ</strong>
                    </div>
                    <div class="preview-row">
                        <span>Tháng cao nhất:</span>
                        <strong id="preview-max">—</strong>
                    </div>
                    <div class="preview-row">
                        <span>Tháng thấp nhất:</span>
                        <strong id="preview-min">—</strong>
                    </div>
                </div>

                <button type="submit" class="btn" style="margin-top: 20px;">💾 Lưu cấu hình</button>
            </form>
        </div>
    </div>

    <script>
        const loanInput = document.getElementById('yearly_loan');
        loanInput.addEventListener('input', updatePreview);
        document.querySelectorAll('.weight-input').forEach(inp => inp.addEventListener('input', updatePreview));

        function getWeights() {{
            const w = {{}};
            document.querySelectorAll('.weight-input').forEach(inp => {{
                w[inp.dataset.month] = parseFloat(inp.value) || 0;
            }});
            return w;
        }}

        function updatePreview() {{
            const yearly = parseInt(loanInput.value) || 0;
            const monthly = yearly / 12;
            const w = getWeights();
            const vals = Object.values(w);
            const avgW = vals.reduce((a, b) => a + b, 0) / 12;

            let maxVal = 0, minVal = Infinity, maxMonth = '', minMonth = '';
            const names = ['T1','T2','T3','T4','T5','T6','T7','T8','T9','T10','T11','T12'];
            for (let m = 1; m <= 12; m++) {{
                const wM = w[String(m)] || 0;
                const allocated = avgW > 0 ? Math.round(monthly * wM / avgW) : 0;
                document.getElementById('amount-' + m).textContent = allocated.toLocaleString() + 'đ';
                if (allocated > maxVal) {{ maxVal = allocated; maxMonth = names[m-1]; }}
                if (allocated < minVal) {{ minVal = allocated; minMonth = names[m-1]; }}
            }}

            document.getElementById('preview-yearly').textContent = yearly.toLocaleString() + 'đ';
            document.getElementById('preview-monthly').textContent = Math.round(monthly).toLocaleString() + 'đ';
            document.getElementById('preview-max').textContent = maxMonth + ': ' + maxVal.toLocaleString() + 'đ';
            document.getElementById('preview-min').textContent = minMonth + ': ' + minVal.toLocaleString() + 'đ';
        }}

        function resetWeights() {{
            document.querySelectorAll('.weight-input').forEach(inp => inp.value = '1.0');
            updatePreview();
        }}

        function equalizeWeights() {{
            resetWeights();
        }}

        document.getElementById('settingsForm').addEventListener('submit', async (e) => {{
            e.preventDefault();
            const yearly = parseInt(loanInput.value) || 0;
            const weights = getWeights();

            try {{
                const response = await fetch('/api/settings', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ yearly_loan_payment: yearly, monthly_weights: weights }})
                }});

                if (response.ok) {{
                    showAlert('✅ Đã lưu cấu hình thành công!', 'success');
                    setTimeout(() => location.href = '/', 1500);
                }} else {{
                    showAlert('❌ Lỗi khi lưu cấu hình', 'error');
                }}
            }} catch (err) {{
                showAlert('❌ Lỗi: ' + err.message, 'error');
            }}
        }});

        function showAlert(message, type) {{
            const alert = document.getElementById('alert');
            alert.textContent = message;
            alert.className = 'alert ' + type;
            alert.style.display = 'block';
            setTimeout(() => alert.style.display = 'none', 3000);
        }}

        // Initial preview
        updatePreview();
    </script>
</body>
</html>"""
    return html


def create_app():
    """Create aiohttp application."""
    db_conn = _get_connection()
    
    # Ensure products table exists
    create_products_table(db_conn)
    migrate_products_table(db_conn)
    
    app = web.Application()
    
    async def handle_index(request):
        filter_product = request.query.get("product", "").strip().upper() or None
        filter_customer = request.query.get("customer", "").strip() or None
        since_date = request.query.get("since", "2026-05-01").strip() or None
        until_date = request.query.get("until", "").strip() or None
        
        settings = load_settings()
        yearly_loan = settings.get("yearly_loan_payment", 0)
        monthly_weights = settings.get("monthly_weights", DEFAULT_WEIGHTS)
        
        html = generate_dashboard_html(db_conn, filter_product, filter_customer, since_date=since_date, until_date=until_date, yearly_loan=yearly_loan, monthly_weights=monthly_weights)
        return web.Response(text=html, content_type="text/html")
    
    async def handle_customers(request):
        since_date = request.query.get("since", "2026-05-01").strip() or None
        until_date = request.query.get("until", "").strip() or None
        html = generate_customer_profit_html(db_conn, since_date, until_date)
        return web.Response(text=html, content_type="text/html")
    
    async def handle_settings(request):
        settings = load_settings()
        yearly_loan = settings.get("yearly_loan_payment", 0)
        monthly_weights = settings.get("monthly_weights", DEFAULT_WEIGHTS)
        html = generate_settings_html(yearly_loan, monthly_weights)
        return web.Response(text=html, content_type="text/html")

    async def handle_api_settings(request):
        try:
            data = await request.json()
            yearly_loan = int(data.get("yearly_loan_payment", 0))
            if yearly_loan < 0:
                return web.json_response({"error": "Số tiền không hợp lệ"}, status=400)

            # Parse monthly weights
            raw_weights = data.get("monthly_weights", {})
            weights = {}
            for m in range(1, 13):
                v = raw_weights.get(str(m), raw_weights.get(m, 1.0))
                weights[str(m)] = max(0.0, float(v))

            settings = {"yearly_loan_payment": yearly_loan, "monthly_weights": weights}
            if save_settings(settings):
                return web.json_response({"success": True, "yearly_loan_payment": yearly_loan, "monthly_weights": weights})
            else:
                return web.json_response({"error": "Lỗi khi lưu"}, status=500)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)
    
    async def handle_product_detail(request):
        code = request.match_info["code"].upper()
        since_date = request.query.get("since", "2026-05-01").strip() or None
        until_date = request.query.get("until", "").strip() or None
        html = generate_product_detail_html(db_conn, code, since_date=since_date, until_date=until_date)
        return web.Response(text=html, content_type="text/html")
    
    async def handle_customer_detail(request):
        from urllib.parse import unquote
        customer_name = unquote(request.match_info["name"])
        filter_product = request.query.get("product", "").strip().upper() or None
        since_date = request.query.get("since", "2026-05-01").strip() or None
        until_date = request.query.get("until", "").strip() or None
        html = generate_customer_detail_html(db_conn, customer_name, filter_product, since_date, until_date)
        return web.Response(text=html, content_type="text/html")
    
    async def handle_order_detail(request):
        thread_id = int(request.match_info["thread_id"])
        html = generate_order_detail_html(db_conn, thread_id)
        return web.Response(text=html, content_type="text/html")
    
    async def handle_product_cost_update(request):
        code = request.match_info["code"].upper()
        data = await request.post()
        cost_price = int(data.get("cost_price", 0))
        
        upsert_product(db_conn, code, cost_price=cost_price)
        
        raise web.HTTPFound(location=f"/product/{code}")
    
    async def handle_export_orders(request):
        """Export orders to CSV."""
        since_date = request.query.get("since", "2026-05-01").strip() or None
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Mã đơn", "Khách hàng", "Mã SP", "SL", "Giá bán", "Giá vốn", "Doanh thu", "Chi phí", "Lợi nhuận"])
        
        cur = db_conn.execute(
            "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL "
            "AND json IS NOT NULL AND thread_id BETWEEN 460000 AND 480000 "
            "ORDER BY thread_id DESC LIMIT 500"
        )
        
        for row in cur.fetchall():
            thread_id = row[0]
            order = json.loads(row[1])
            created = order.get("created", "")
            
            if since_date and created:
                try:
                    vn_tz = timezone(timedelta(hours=7))
                    if isinstance(created, str):
                        dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                        created_date = dt.astimezone(vn_tz).strftime("%Y-%m-%d")
                    elif created > 1e10:
                        created_date = datetime.fromtimestamp(created / 1000, tz=timezone.utc).astimezone(vn_tz).strftime("%Y-%m-%d")
                    else:
                        created_date = datetime.fromtimestamp(created, tz=timezone.utc).astimezone(vn_tz).strftime("%Y-%m-%d")
                    if created_date < since_date:
                        continue
                except:
                    continue
            
            customer = order.get("customer_name") or order.get("khach_hang") or ""
            if isinstance(customer, dict):
                customer = customer.get("name", "")
            customer = str(customer or "")
            
            result = calculate_order_profit(db_conn, order)
            for item in result["items"]:
                writer.writerow([
                    thread_id, customer, item["code"], item["qty"],
                    item["sell_price"], item["cost_price"],
                    item["revenue"], item["cost"], item["profit"]
                ])
        
        output.seek(0)
        filename = f"orders_profit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return web.Response(
            body=output.getvalue(),
            content_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    
    async def handle_export_products(request):
        """Export products to CSV."""
        products = get_all_products(db_conn)
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Mã SP", "Tên", "Giá vốn", "Ghi chú"])
        
        for p in products:
            writer.writerow([p["code"], p["name"], p["cost_price"], p["note"]])
        
        output.seek(0)
        filename = f"products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return web.Response(
            body=output.getvalue(),
            content_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    
    async def handle_api_products(request):
        products = get_all_products(db_conn)
        return web.json_response(products)
    
    async def handle_api_product_update(request):
        data = await request.json()
        code = data.get("code", "").upper()
        cost_price = data.get("cost_price")
        name = data.get("name")
        
        if not code:
            return web.json_response({"error": "Missing code"}, status=400)
        
        ok = upsert_product(db_conn, code, name=name, cost_price=cost_price)
        return web.json_response({"ok": ok, "code": code})
    
    async def handle_api_profit(request):
        thread_id = request.query.get("thread_id")
        if not thread_id:
            return web.json_response({"error": "Missing thread_id"}, status=400)
        
        order = get_order_by_thread_id(db_conn, int(thread_id))
        if not order:
            return web.json_response({"error": "Order not found"}, status=404)
        
        result = calculate_order_profit(db_conn, order)
        return web.json_response(result)
    
    async def handle_products_bulk_update(request):
        """Bulk update cost prices from products tab."""
        data = await request.post()
        updated = 0
        for key, value in data.items():
            if key.startswith("cost_") and value.strip():
                code = key[5:].upper()  # Remove 'cost_' prefix
                try:
                    cost_price = int(value.replace(",", "").replace(".", ""))
                    if cost_price >= 0:
                        upsert_product(db_conn, code, cost_price=cost_price)
                        updated += 1
                except ValueError:
                    continue
        
        # Redirect back to dashboard with products tab
        raise web.HTTPFound(location="/?tab=products")
    
    async def handle_freeze_costs(request):
        """Freeze cost prices into all orders that don't have frozen prices."""
        from product_db import freeze_invoice_cost_prices
        
        cur = db_conn.execute(
            "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL "
            "AND json IS NOT NULL AND thread_id BETWEEN 460000 AND 480000"
        )
        
        updated = 0
        for row in cur.fetchall():
            thread_id = row[0]
            order = json.loads(row[1])
            invoice = order.get("invoice") or []
            
            if not invoice:
                continue
            
            # Check if any item needs freezing
            needs_freeze = any("cost_price" not in item for item in invoice)
            if not needs_freeze:
                continue
            
            # Freeze cost prices
            frozen_invoice = freeze_invoice_cost_prices(db_conn, invoice)
            order["invoice"] = frozen_invoice
            
            # Save back to database
            from order_db import _save_order
            if _save_order(db_conn, thread_id, order):
                updated += 1
        
        return web.json_response({"ok": True, "updated": updated})
    
    async def handle_api_orders(request):
        """API endpoint for paginated orders (infinite scroll)."""
        page = int(request.query.get("page", 1))
        per_page = int(request.query.get("per_page", 50))
        since_date = request.query.get("since", "2026-05-01").strip() or None
        until_date = request.query.get("until", "").strip() or None
        filter_product = request.query.get("product", "").strip().upper() or None
        filter_customer = request.query.get("customer", "").strip() or None
        
        # Get all orders first, then paginate
        cur = db_conn.execute(
            "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL "
            "AND json IS NOT NULL AND thread_id BETWEEN 460000 AND 480000 "
            "ORDER BY thread_id DESC"
        )
        
        all_orders = []
        for row in cur.fetchall():
            thread_id = row[0]
            order = json.loads(row[1])
            created = order.get("created", "")
            
            # Filter by date range (VN timezone UTC+7)
            if created:
                try:
                    vn_tz = timezone(timedelta(hours=7))
                    if isinstance(created, str):
                        dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                        created_date = dt.astimezone(vn_tz).strftime("%Y-%m-%d")
                    elif created > 1e10:
                        created_date = datetime.fromtimestamp(created / 1000, tz=timezone.utc).astimezone(vn_tz).strftime("%Y-%m-%d")
                    else:
                        created_date = datetime.fromtimestamp(created, tz=timezone.utc).astimezone(vn_tz).strftime("%Y-%m-%d")
                    if since_date and created_date < since_date:
                        continue
                    if until_date and created_date > until_date:
                        continue
                except:
                    continue
            
            result = calculate_order_profit(db_conn, order)
            if not result["items"]:
                continue
            
            customer = order.get("customer_name") or order.get("khach_hang") or ""
            if isinstance(customer, dict):
                customer = customer.get("name", "")
            customer = str(customer or "")
            
            # Filter by product
            if filter_product:
                has_product = any(item["code"] == filter_product for item in result["items"])
                if not has_product:
                    continue
            
            # Filter by customer
            if filter_customer and filter_customer.lower() not in customer.lower():
                continue
            
            # Format date + time (VN timezone UTC+7)
            if created:
                try:
                    vn_tz = timezone(timedelta(hours=7))
                    if isinstance(created, str):
                        dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                        vn = dt.astimezone(vn_tz)
                        date_display = vn.strftime("%d/%m %H:%M")
                    elif created > 1e10:
                        dt = datetime.fromtimestamp(created / 1000, tz=timezone.utc)
                        vn = dt.astimezone(vn_tz)
                        date_display = vn.strftime("%d/%m %H:%M")
                    else:
                        dt = datetime.fromtimestamp(created, tz=timezone.utc)
                        vn = dt.astimezone(vn_tz)
                        date_display = vn.strftime("%d/%m %H:%M")
                except:
                    date_display = ""
            else:
                date_display = ""
            
            # Build items summary with full data for modal
            items_summary = []
            for item in result["items"]:
                items_summary.append({
                    "code": item["code"],
                    "qty": item["qty"],
                    "sell_price": item["sell_price"],
                    "cost_price": item["cost_price"],
                    "revenue": item["revenue"],
                    "cost": item["cost"],
                    "profit": item["profit"],
                    "has_cost": item["has_cost"],
                })
            
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
            })
        
        # Paginate
        start = (page - 1) * per_page
        end = start + per_page
        orders_page = all_orders[start:end]
        has_more = end < len(all_orders)
        
        return web.json_response({
            "orders": orders_page,
            "page": page,
            "has_more": has_more,
            "total": len(all_orders)
        })
    
    app.router.add_get("/", handle_index)
    app.router.add_get("/customers", handle_customers)
    app.router.add_get("/settings", handle_settings)
    app.router.add_post("/api/settings", handle_api_settings)
    app.router.add_get("/product/{code}", handle_product_detail)
    app.router.add_get("/customer/{name}", handle_customer_detail)
    app.router.add_get("/order/{thread_id}", handle_order_detail)
    app.router.add_post("/product/{code}/cost", handle_product_cost_update)
    app.router.add_post("/products/bulk-update", handle_products_bulk_update)
    app.router.add_get("/export/orders", handle_export_orders)
    app.router.add_get("/export/products", handle_export_products)
    app.router.add_get("/api/orders", handle_api_orders)
    app.router.add_get("/api/products", handle_api_products)
    app.router.add_post("/api/products", handle_api_product_update)
    app.router.add_get("/api/profit", handle_api_profit)
    app.router.add_post("/api/freeze-costs", handle_freeze_costs)
    
    return app


def start_dashboard():
    """Start the dashboard web server."""
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=DASHBOARD_PORT, print=lambda msg: log.info(msg))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_dashboard()
