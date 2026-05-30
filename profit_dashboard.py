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
import json
import logging
import os
from aiohttp import web
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

from order_db import _get_connection, get_order_by_thread_id
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


def _format_money(n: int) -> str:
    return f"{n:,}"


def generate_dashboard_html(db_conn, filter_product=None, filter_customer=None, limit=100, since_date=None, until_date=None):
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
        
        # Filter by date range
        created = order.get("created", "")
        if created:
            try:
                if isinstance(created, str):
                    created_date = created[:10]  # Get YYYY-MM-DD part
                elif created > 1e10:
                    created_date = datetime.fromtimestamp(created / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                else:
                    created_date = datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%d")
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
    
    # Build HTML
    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard Lợi Nhuận</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{ color: #333; margin-bottom: 20px; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px; }}
        .card {{ background: white; border-radius: 10px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .card h3 {{ color: #666; font-size: 14px; margin-bottom: 10px; }}
        .card .value {{ font-size: 24px; font-weight: bold; }}
        .card .value.positive {{ color: #22c55e; }}
        .card .value.negative {{ color: #ef4444; }}
        .nav {{ margin-bottom: 20px; }}
        .nav a {{ padding: 8px 16px; background: #3b82f6; color: white; text-decoration: none; border-radius: 5px; margin-right: 10px; }}
        .nav a:hover {{ background: #2563eb; }}
        .nav a.active {{ background: #1d4ed8; }}
        .filters {{ background: white; border-radius: 10px; padding: 15px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .filters input, .filters button {{ padding: 8px 12px; border: 1px solid #ddd; border-radius: 5px; margin-right: 10px; }}
        .filters button {{ background: #3b82f6; color: white; cursor: pointer; }}
        .filters button:hover {{ background: #2563eb; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 30px; }}
        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f9fa; font-weight: 600; color: #333; }}
        tr:hover {{ background: #f5f5f5; }}
        .profit {{ font-weight: 600; }}
        .profit.positive {{ color: #22c55e; }}
        .profit.negative {{ color: #ef4444; }}
        .tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; }}
        .tag.green {{ background: #dcfce7; color: #166534; }}
        .tag.red {{ background: #fee2e2; color: #991b1b; }}
        .tag.yellow {{ background: #fef9c3; color: #854d0e; }}
        .section {{ margin-bottom: 30px; }}
        .section h2 {{ color: #333; margin-bottom: 15px; font-size: 18px; }}
        .tabs {{ display: flex; gap: 10px; margin-bottom: 20px; }}
        .tab {{ padding: 10px 20px; background: white; border: none; border-radius: 5px; cursor: pointer; font-size: 14px; }}
        .tab.active {{ background: #3b82f6; color: white; }}
        .tab:hover {{ background: #e5e7eb; }}
        .tab.active:hover {{ background: #2563eb; }}
        @media (max-width: 768px) {{
            .summary {{ grid-template-columns: 1fr 1fr; }}
            table {{ font-size: 14px; }}
            th, td {{ padding: 8px 10px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/" class="active">🏠 Dashboard</a>
            <a href="/customers">👥 Khách hàng</a>
            <a href="/export/orders">📥 Export Orders</a>
            <a href="/export/products">📥 Export Products</a>
        </div>
        <h1>📊 Dashboard Lợi Nhuận</h1>
        
        <div class="filters">
            <form method="GET" action="/">
                <input type="date" name="since" value="{since_date or '2026-05-01'}" title="Từ ngày">
                <input type="date" name="until" value="{until_date or ''}" title="Đến ngày">
                <input type="text" name="product" placeholder="Lọc theo mã SP" value="{filter_product or ''}">
                <input type="text" name="customer" placeholder="Lọc theo khách hàng" value="{filter_customer or ''}">
                <button type="submit">🔍 Lọc</button>
                <a href="/" style="padding: 8px 12px; text-decoration: none; color: #3b82f6;">Xóa bộ lọc</a>
            </form>
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
                <h3>📋 Đơn hàng</h3>
                <div class="value">{len(orders_data)}</div>
            </div>
        </div>
        
        <div class="tabs">
            <button class="tab active" onclick="showTab('orders')">Đơn hàng</button>
            <button class="tab" onclick="showTab('products')">Sản phẩm</button>
        </div>
        
        <div id="orders-tab" class="section">
            <h2>📋 Lợi nhuận theo đơn hàng</h2>
            <table>
                <thead>
                    <tr>
                        <th>Đơn hàng</th>
                        <th>Ngày</th>
                        <th>Khách hàng</th>
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
        # Format date
        created = od.get('created', '')
        if created:
            try:
                if isinstance(created, str):
                    date_display = created[:10]  # YYYY-MM-DD
                elif created > 1e10:
                    date_display = datetime.fromtimestamp(created / 1000, tz=timezone.utc).strftime("%d/%m/%Y")
                else:
                    date_display = datetime.fromtimestamp(created, tz=timezone.utc).strftime("%d/%m/%Y")
            except:
                date_display = ""
        else:
            date_display = ""
        
        html += f"""
                    <tr>
                        <td><a href="tg://privatepost?channel=2124542200&post={od['thread_id']}" target="_blank">#{od['thread_id']}</a></td>
                        <td>{date_display}</td>
                        <td>{customer_name}</td>
                        <td>{_format_money(od['revenue'])}đ</td>
                        <td>{_format_money(od['cost'])}đ</td>
                        <td class="profit {profit_class}">{profit_display}</td>
                        <td>{margin:.1f}%</td>
                    </tr>"""
    
    html += """
                </tbody>
            </table>
        </div>
        
        <div id="products-tab" class="section" style="display:none">
            <h2>📦 Lợi nhuận theo sản phẩm</h2>
            <form method="POST" action="/products/bulk-update">
                <div style="margin-bottom: 10px;">
                    <button type="submit" style="padding: 8px 16px; background: #22c55e; color: white; border: none; border-radius: 5px; cursor: pointer;">💾 Lưu tất cả giá vốn</button>
                    <button type="button" onclick="selectAllWithCost()" style="padding: 8px 16px; background: #3b82f6; color: white; border: none; border-radius: 5px; cursor: pointer; margin-left: 10px;">Chọn SP chưa có giá vốn</button>
                </div>
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
            </form>
        </div>
    </div>
    
    <script>
    function selectAllWithCost() {
        document.querySelectorAll('input.no-cost').forEach(el => el.focus());
    }
    </script>
    
    <script>
    function showTab(tab) {
        document.getElementById('orders-tab').style.display = tab === 'orders' ? 'block' : 'none';
        document.getElementById('products-tab').style.display = tab === 'products' ? 'block' : 'none';
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        event.target.classList.add('active');
    }
    
    // Check URL params for tab
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('tab') === 'products') {
        showTab('products');
        document.querySelectorAll('.tab')[1].classList.add('active');
    }
    </script>
</body>
</html>"""
    
    return html


def generate_product_detail_html(db_conn, product_code):
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
        "ORDER BY thread_id DESC LIMIT 500"
    )
    
    orders_with_product = []
    total_qty = 0
    total_revenue = 0
    total_cost = 0
    total_profit = 0
    
    for row in cur.fetchall():
        thread_id = row[0]
        order = json.loads(row[1])
        
        invoice = order.get("invoice") or order.get("invoice_items") or []
        for item in invoice:
            if (item.get("sp") or "").upper().strip() == product_code:
                qty = int(item.get("sl", 0))
                sell_price = int(item.get("price", 0))
                revenue = qty * sell_price
                cost = qty * product["cost_price"]
                profit = revenue - cost
                
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
                total_profit += profit if product['cost_price'] > 0 else 0
    
    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chi tiết sản phẩm {product_code}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #333; margin-bottom: 20px; }}
        .back {{ color: #3b82f6; text-decoration: none; margin-bottom: 20px; display: inline-block; }}
        .nav {{ margin-bottom: 20px; }}
        .nav a {{ padding: 8px 16px; background: #3b82f6; color: white; text-decoration: none; border-radius: 5px; margin-right: 10px; }}
        .nav a:hover {{ background: #2563eb; }}
        .product-info {{ background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 20px; }}
        .card {{ background: white; border-radius: 10px; padding: 15px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .card h3 {{ color: #666; font-size: 12px; margin-bottom: 5px; }}
        .card .value {{ font-size: 20px; font-weight: bold; }}
        .card .value.positive {{ color: #22c55e; }}
        .card .value.negative {{ color: #ef4444; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f9fa; font-weight: 600; color: #333; }}
        tr:hover {{ background: #f5f5f5; }}
        .profit {{ font-weight: 600; }}
        .profit.positive {{ color: #22c55e; }}
        .profit.negative {{ color: #ef4444; }}
        .form {{ background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .form input, .form button {{ padding: 8px 12px; border: 1px solid #ddd; border-radius: 5px; margin-right: 10px; }}
        .form button {{ background: #3b82f6; color: white; cursor: pointer; }}
        .form button:hover {{ background: #2563eb; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/">🏠 Dashboard</a>
            <a href="/customers">👥 Khách hàng</a>
        </div>
        <h1>📦 Sản phẩm: {product_code}</h1>
        
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
                <tr>
                    <td><a href="tg://privatepost?channel=2124542200&post={od['thread_id']}" target="_blank">#{od['thread_id']}</a></td>
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
        
        # Filter by date range
        if created:
            try:
                if isinstance(created, str):
                    created_date = created[:10]
                elif created > 1e10:
                    created_date = datetime.fromtimestamp(created / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                else:
                    created_date = datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%d")
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
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #333; margin-bottom: 20px; }}
        .nav {{ margin-bottom: 20px; }}
        .nav a {{ padding: 8px 16px; background: #3b82f6; color: white; text-decoration: none; border-radius: 5px; margin-right: 10px; }}
        .nav a:hover {{ background: #2563eb; }}
        .nav a.active {{ background: #1d4ed8; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px; }}
        .card {{ background: white; border-radius: 10px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .card h3 {{ color: #666; font-size: 14px; margin-bottom: 10px; }}
        .card .value {{ font-size: 24px; font-weight: bold; }}
        .card .value.positive {{ color: #22c55e; }}
        .card .value.negative {{ color: #ef4444; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f9fa; font-weight: 600; color: #333; }}
        tr:hover {{ background: #f5f5f5; }}
        .profit {{ font-weight: 600; }}
        .profit.positive {{ color: #22c55e; }}
        .profit.negative {{ color: #ef4444; }}
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
            <form method="GET" action="/customers">
                <input type="date" name="since" value="{since_date or '2026-05-01'}" title="Từ ngày">
                <input type="date" name="until" value="{until_date or ''}" title="Đến ngày">
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
        
        html = generate_dashboard_html(db_conn, filter_product, filter_customer, since_date=since_date, until_date=until_date)
        return web.Response(text=html, content_type="text/html")
    
    async def handle_customers(request):
        since_date = request.query.get("since", "2026-05-01").strip() or None
        until_date = request.query.get("until", "").strip() or None
        html = generate_customer_profit_html(db_conn, since_date, until_date)
        return web.Response(text=html, content_type="text/html")
    
    async def handle_product_detail(request):
        code = request.match_info["code"].upper()
        html = generate_product_detail_html(db_conn, code)
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
                    if isinstance(created, str):
                        created_date = created[:10]
                    elif created > 1e10:
                        created_date = datetime.fromtimestamp(created / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                    else:
                        created_date = datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%d")
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
    
    app.router.add_get("/", handle_index)
    app.router.add_get("/customers", handle_customers)
    app.router.add_get("/product/{code}", handle_product_detail)
    app.router.add_post("/product/{code}/cost", handle_product_cost_update)
    app.router.add_post("/products/bulk-update", handle_products_bulk_update)
    app.router.add_get("/export/orders", handle_export_orders)
    app.router.add_get("/export/products", handle_export_products)
    app.router.add_get("/api/products", handle_api_products)
    app.router.add_post("/api/products", handle_api_product_update)
    app.router.add_get("/api/profit", handle_api_profit)
    
    return app


def start_dashboard():
    """Start the dashboard web server."""
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=DASHBOARD_PORT, print=lambda msg: log.info(msg))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_dashboard()
