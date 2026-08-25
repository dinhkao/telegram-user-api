"""Main dashboard page generator: generate_dashboard_html."""
from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

from product_db import get_all_products, calculate_order_profit

from profit_dashboard.utils import calc_prorated_loan, _format_money, _get_date_presets_html, _get_preset_highlight_js, _page_head, _nav_html, _set_date_preset_js, resolve_customer_name


def generate_dashboard_html(db_conn, filter_product=None, filter_customer=None, limit=2000, since_date=None, until_date=None, yearly_loan=0, monthly_weights=None):
    """Generate the main dashboard HTML."""
    
    # Get all products
    products = get_all_products(db_conn)
    product_map = {p["code"]: p for p in products}
    
    # Get orders with profit (use thread_id for sorting as it's sequential)
    cur = db_conn.execute(
        "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL "
        "AND json IS NOT NULL AND thread_id >= 460000 "
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
        since_date = datetime.now().strftime("%Y-%m-%d")
    
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
        
        customer = resolve_customer_name(db_conn, order)
        
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
            "order_text": (order.get("text") or "").strip()[:80],
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
            "AND json IS NOT NULL AND thread_id >= 460000 "
            "ORDER BY thread_id DESC LIMIT 2000"
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
            customer = resolve_customer_name(db_conn, order) or "Khách lẻ"
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
            "AND json IS NOT NULL AND thread_id >= 460000 "
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
            customer = resolve_customer_name(db_conn, order) or "Khách lẻ"
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
    top_nav, bottom_nav = _nav_html('dashboard')

    extra_css = """
        tr { cursor: pointer; }
        .change { font-size: 12px; margin-top: 6px; font-weight: 600; display: flex; align-items: center; gap: 4px; justify-content: center; flex-wrap: wrap; }
        .change.up { color: rgb(var(--positive)); }
        .change.down { color: rgb(var(--negative)); }
        .change.new { color: rgb(var(--accent)); }
        .change-label { color: rgb(var(--text-faint)); font-weight: 400; font-size: 11px; }
        .top-performers { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; }
        .real-profit-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important; color: white; }
        .real-profit-card h3 { color: rgba(255,255,255,0.9); }
        .real-profit-card .value { color: white; }
        .loan-info { font-size: 11px; margin-top: 6px; opacity: 0.95; display: flex; flex-direction: column; gap: 2px; align-items: center; }
        .margin-badge { background: rgba(255,255,255,0.2); padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 600; }
        .performer-section { border-radius: 8px; padding: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); background: rgb(var(--surface)); }
        .performer-section h3 { margin-bottom: 8px; font-size: 13px; color: rgb(var(--text-heading)); }
        .performer-list { display: flex; flex-direction: column; gap: 4px; }
        .performer-item { display: flex; align-items: center; gap: 8px; padding: 4px; border-radius: 4px; transition: background-color 0.2s; }
        .performer-item:hover { background: rgb(var(--surface-hover)); }
        .performer-rank { background: linear-gradient(135deg, #3b82f6, #1d4ed8); color: white; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 11px; flex-shrink: 0; }
        .performer-item:nth-child(1) .performer-rank { background: linear-gradient(135deg, #fbbf24, #f59e0b); }
        .performer-item:nth-child(2) .performer-rank { background: linear-gradient(135deg, #94a3b8, #64748b); }
        .performer-item:nth-child(3) .performer-rank { background: linear-gradient(135deg, #fb923c, #ea580c); }
        .performer-info { flex: 1; min-width: 0; }
        .performer-name { font-weight: 600; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: rgb(var(--text-heading)); }
        .performer-stats { display: flex; gap: 8px; margin-top: 1px; font-size: 11px; color: rgb(var(--text-muted)); }
        .prod-chips { display: flex; flex-wrap: wrap; gap: 4px; max-width: 220px; }
        .prod-chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 500; line-height: 1.2; white-space: nowrap; }
        .prod-chip .code { color: rgb(var(--accent)); }
        .prod-chip .qty { color: rgb(var(--text-muted)); }
        .prod-chip.ok { background: rgb(var(--chip-ok-bg)); }
        .prod-chip.warn { background: rgb(var(--chip-warn-bg)); }
        .prod-chip.warn .code { color: rgb(var(--tag-yellow-text)); }
        .prod-chip.warn .qty { color: rgb(var(--tag-yellow-text)); }
        .tabs { display: flex; gap: 4px; margin-bottom: 10px; }
        .tab { padding: 6px 12px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; background: rgb(var(--surface)); color: rgb(var(--text)); }
        .tab.active { background: rgb(var(--accent)); color: white; }
        .tab:hover { background: rgb(var(--surface-2)); }
        .tab.active:hover { filter: brightness(0.9); }
        .chart-controls { display: flex; gap: 4px; margin-bottom: 8px; }
        .chart-toggle { padding: 4px 10px; border: 1px solid rgb(var(--border)); border-radius: 4px; cursor: pointer; font-size: 11px; background: rgb(var(--surface)); color: rgb(var(--text)); }
        .chart-toggle.active { background: rgb(var(--accent)); color: white; border-color: rgb(var(--accent)); }
        .chart-wrap { border-radius: 6px; padding: 12px; box-shadow: 0 1px 6px rgba(0,0,0,0.08); background: rgb(var(--surface)); }
        @media (max-width: 768px) {
            .tab { font-size: 12px; padding: 4px 10px; }
            .top-performers { grid-template-columns: 1fr; gap: 8px; }
        }
    """

    html = _page_head("Dashboard Lợi Nhuận", extra_css=extra_css, chart=True)
    html += f"""
<body>
    <div class="container">
        {top_nav}
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
                <button type="button" onclick="setDatePreset('month_1')">Tháng 1</button>
                <button type="button" onclick="setDatePreset('month_2')">Tháng 2</button>
                <button type="button" onclick="setDatePreset('month_3')">Tháng 3</button>
                <button type="button" onclick="setDatePreset('month_4')">Tháng 4</button>
                <button type="button" onclick="setDatePreset('month_5')">Tháng 5</button>
                <button type="button" onclick="setDatePreset('month_6')">Tháng 6</button>
                <button type="button" onclick="setDatePreset('month_7')">Tháng 7</button>
                <button type="button" onclick="setDatePreset('month_8')">Tháng 8</button>
                <button type="button" onclick="setDatePreset('month_9')">Tháng 9</button>
                <button type="button" onclick="setDatePreset('month_10')">Tháng 10</button>
                <button type="button" onclick="setDatePreset('month_11')">Tháng 11</button>
                <button type="button" onclick="setDatePreset('month_12')">Tháng 12</button>
            </div>
            <form method="GET" action="/loi-nhuan/">
                <input type="date" name="since" id="since" value="{since_date or datetime.now().strftime('%Y-%m-%d')}" title="Từ ngày" onchange="this.form.submit()">
                <input type="date" name="until" id="until" value="{until_date or ''}" title="Đến ngày" onchange="this.form.submit()">
                <input type="text" name="product" placeholder="Lọc theo mã SP" value="{filter_product or ''}" oninput="debounceFilter(this)">
                <input type="text" name="customer" placeholder="Lọc theo khách hàng" value="{filter_customer or ''}" oninput="debounceFilter(this)">
                <button type="submit">🔍 Lọc</button>
                <a href="/loi-nhuan/" style="padding: 8px 12px; text-decoration: none; color: rgb(var(--accent));">Xóa bộ lọc</a>
                <button type="button" onclick="freezeAllCosts()" style="padding: 8px 16px; background: rgb(var(--warning)); color: white; border: none; border-radius: 5px; cursor: pointer; margin-left: 10px;">🔒 Đóng băng giá vốn</button>
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
                    <div class="performer-item" onclick="location.href='/loi-nhuan/customer/{quote(cust)}'" style="cursor: pointer;">
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
            has_item_cost = item.get('has_cost', False)
            chip_cls = "prod-chip ok" if has_item_cost else "prod-chip warn"
            product_details.append(f'<span class="{chip_cls}"><span class="code">{code}</span><span class="qty">×{qty}</span></span>')
        products_html = f'<div class="prod-chips">{" ".join(product_details)}</div>' if product_details else "-"
        
        # Build items JSON for modal - escape for HTML attribute
        items_json = json.dumps(items).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace(chr(39), '&#39;')
        
        # Get fees for the order
        vat = int(order.get("vat", 0))
        pvc = int(order.get("pvc", 0))
        disc = int(order.get("discount", 0))
        fees_obj = {"vat": vat, "pvc": pvc, "discount": disc}
        fees_json = json.dumps(fees_obj).replace('"', '&quot;').replace(chr(39), '&#39;')
        
        # Get order text for display
        order_text = od.get('order_text', '')
        order_text_html = f'<br><small style="color:rgb(var(--text-faint)); font-size:10px; line-height:1.2;">{order_text}</small>' if order_text else ''
        
        html += f"""
                    <tr onclick="showOrderDetail({od['thread_id']}, &#39;{customer_name}&#39;, &#39;{date_display}&#39;, {od['revenue']}, {od['cost']}, {od['profit']}, {items_json}, {fees_json})" style="cursor: pointer;">
                        <td><a href="tg://privatepost?channel=2124542200&post={od['thread_id']}" target="_blank" onclick="event.stopPropagation()">#{od['thread_id']}</a></td>
                        <td>{date_display}</td>
                        <td><a href="/loi-nhuan/customer/{customer_url}" style="color: rgb(var(--accent)); text-decoration: none;" onclick="event.stopPropagation()">{customer_name}</a>{order_text_html}</td>
                        <td>{products_html}</td>
                        <td>{_format_money(od['revenue'])}đ</td>
                        <td>{_format_money(od['cost'])}đ</td>
                        <td class="profit {profit_class}">{profit_display}</td>
                        <td>{margin:.1f}%</td>
                    </tr>"""
    
    html += """
                    <tr id="loading-row" style="display:none;">
                        <td colspan="8" style="text-align:center; padding: 12px;">
                            <div class="spinner"></div> Đang tải thêm...
                        </td>
                    </tr>
                </tbody>
            </table>
            </div>
        </div>
        
        <div id="products-tab" class="section" style="display:none">
            <h2>📦 Lợi nhuận theo sản phẩm</h2>
            <form method="POST" action="/loi-nhuan/products/bulk-update">
                <div style="margin-bottom: 10px;">
                    <button type="submit" style="padding: 8px 16px; background: rgb(var(--positive)); color: white; border: none; border-radius: 5px; cursor: pointer;">💾 Lưu tất cả giá vốn</button>
                    <button type="button" onclick="selectAllWithCost()" style="padding: 8px 16px; background: rgb(var(--accent)); color: white; border: none; border-radius: 5px; cursor: pointer; margin-left: 10px;">Chọn SP chưa có giá vốn</button>
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
                        <td><a href="/loi-nhuan/product/{code}">Chi tiết</a></td>
                    </tr>"""
    
    html += """
                    </tbody>
                </table>
                </div>
            </form>
        </div>
    </div>
    
    <div id="chart-tab" class="section" style="display:none">
        <h2>📊 Biểu đồ lợi nhuận</h2>
        <div class="chart-controls">
            <button class="chart-toggle active" onclick="setChartAgg('daily', this)">Ngày</button>
            <button class="chart-toggle" onclick="setChartAgg('weekly', this)">Tuần</button>
            <button class="chart-toggle" onclick="setChartAgg('monthly', this)">Tháng</button>
        </div>
        <div class="chart-wrap">
            <canvas id="profitChart" style="width:100%; max-height:400px;"></canvas>
        </div>
    </div>
    
    <!-- Order Detail Modal -->
    <div id="orderModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1000; overflow:auto;">
        <div class="modal-content" style="background:rgb(var(--surface)); margin:20px auto; max-width:95%; width:700px; border-radius:6px; padding:12px; position:relative; color:rgb(var(--text));">
            <button onclick="closeModal()" style="position:absolute; top:8px; right:12px; background:none; border:none; font-size:28px; cursor:pointer; line-height:1; padding:4px; color:rgb(var(--text));">✕</button>
            <h2 id="modal-title" style="margin-bottom:16px; font-size:18px; color:rgb(var(--text-heading));">Chi tiết đơn hàng</h2>
            <div id="modal-content" style="overflow-x:auto;"></div>
        </div>
    </div>
    
    <script>
    // Debounced auto-submit for filter inputs
    const _filterTimers = {};
    function debounceFilter(el) {
        const key = el.name;
        clearTimeout(_filterTimers[key]);
        _filterTimers[key] = setTimeout(() => el.form.submit(), 300);
    }
    
    function selectAllWithCost() {
        document.querySelectorAll('input.no-cost').forEach(el => el.focus());
    }
    </script>
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
    let currentAgg = 'daily';

    function aggregateData(data, mode) {
        if (mode === 'daily') return data;
        const groups = {};
        data.forEach(d => {
            let key;
            if (mode === 'weekly') {
                const dt = new Date(d.full_day);
                const mon = new Date(dt); mon.setDate(dt.getDate() - dt.getDay() + 1);
                key = mon.toISOString().slice(5,10);
            } else {
                key = d.full_day.slice(0,7);
            }
            if (!groups[key]) groups[key] = {day: key, revenue: 0, cost: 0, profit: 0, real_profit: 0};
            groups[key].revenue += d.revenue;
            groups[key].cost += d.cost;
            groups[key].profit += d.profit;
            groups[key].real_profit += d.real_profit;
        });
        return Object.values(groups);
    }

    function setChartAgg(mode, btn) {
        currentAgg = mode;
        document.querySelectorAll('.chart-toggle').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        if (profitChart) { profitChart.destroy(); profitChart = null; }
        renderChart();
    }

    function renderChart() {
        if (profitChart) return;
        const agg = aggregateData(chartData, currentAgg);
        const ctx = document.getElementById('profitChart').getContext('2d');
        const isDark = document.documentElement.classList.contains('dark');
        const gridColor = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)';
        const textColor = isDark ? '#b4b4be' : '#666';
        profitChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: agg.map(d => d.day),
                datasets: [
                    { label: 'Doanh thu', data: agg.map(d => d.revenue), backgroundColor: 'rgba(59,130,246,0.7)', borderColor: '#3b82f6', borderWidth: 1 },
                    { label: 'Giá vốn', data: agg.map(d => d.cost), backgroundColor: 'rgba(239,68,68,0.5)', borderColor: '#ef4444', borderWidth: 1 },
                    { label: 'Lợi nhuận', data: agg.map(d => d.profit), backgroundColor: 'rgba(34,197,94,0.7)', borderColor: '#22c55e', borderWidth: 1 },
                    { label: 'LN sau vay', data: agg.map(d => d.real_profit), backgroundColor: 'rgba(168,85,247,0.7)', borderColor: '#a855f7', borderWidth: 1 },
                    { label: 'Biên LN %', data: agg.map(d => d.revenue > 0 ? (d.profit / d.revenue * 100) : 0), type: 'line', yAxisID: 'pct', borderColor: '#f59e0b', backgroundColor: 'transparent', borderWidth: 2, pointRadius: 2, tension: 0.3 }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top', labels: { color: textColor } },
                    tooltip: { callbacks: { label: ctx => ctx.dataset.yAxisID === 'pct' ? ctx.dataset.label + ': ' + ctx.raw.toFixed(1) + '%' : ctx.dataset.label + ': ' + ctx.raw.toLocaleString() + 'đ' } }
                },
                scales: {
                    y: { ticks: { callback: v => (v / 1000000).toFixed(1) + 'M', color: textColor }, grid: { color: gridColor } },
                    pct: { position: 'right', ticks: { callback: v => v.toFixed(0) + '%', color: textColor }, grid: { drawOnChartArea: false } },
                    x: { ticks: { color: textColor }, grid: { color: gridColor } }
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

    """ + _set_date_preset_js('.filters form') + """

    // Freeze all cost prices
    function freezeAllCosts() {
        if (!confirm('Đóng băng giá vốn vào tất cả đơn hàng? Giá vốn hiện tại sẽ được lưu vào đơn hàng và không thay đổi khi bạn cập nhật giá mới.')) {
            return;
        }
        
        fetch('/loi-nhuan/api/freeze-costs', { method: 'POST' })
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
                        <tr style="background:rgb(var(--surface-hover));">
                            <th style="padding:8px; text-align:left; border-bottom:1px solid rgb(var(--border)); color:rgb(var(--text-heading));">Mã SP</th>
                            <th style="padding:8px; text-align:right; border-bottom:1px solid rgb(var(--border)); color:rgb(var(--text-heading));">SL</th>
                            <th style="padding:8px; text-align:right; border-bottom:1px solid rgb(var(--border)); color:rgb(var(--text-heading));">Giá bán</th>
                            <th style="padding:8px; text-align:right; border-bottom:1px solid rgb(var(--border)); color:rgb(var(--text-heading));">Giá vốn</th>
                            <th style="padding:8px; text-align:right; border-bottom:1px solid rgb(var(--border)); color:rgb(var(--text-heading));">Doanh thu</th>
                            <th style="padding:8px; text-align:right; border-bottom:1px solid rgb(var(--border)); color:rgb(var(--text-heading));">Chi phí</th>
                            <th style="padding:8px; text-align:right; border-bottom:1px solid rgb(var(--border)); color:rgb(var(--text-heading));">Lợi nhuận</th>
                            <th style="padding:8px; text-align:right; border-bottom:1px solid rgb(var(--border)); color:rgb(var(--text-heading));">%LN</th>
                        </tr>
                    </thead>
                    <tbody>`;

            items.forEach(item => {
                const itemRevenue = item.revenue || (item.qty * item.sell_price);
                const itemCost = item.cost || (item.qty * item.cost_price);
                const itemProfit = item.profit || (item.has_cost ? itemRevenue - itemCost : 0);
                const itemMargin = item.has_cost && itemRevenue > 0 ? ((itemProfit / itemRevenue) * 100).toFixed(1) : 0;
                const profitClass = itemProfit > 0 ? 'color:rgb(var(--positive))' : (itemProfit < 0 ? 'color:rgb(var(--negative))' : '');

                itemsHtml += `
                    <tr>
                        <td style="padding:8px; border-bottom:1px solid rgb(var(--border)); color:rgb(var(--text));"><strong>${item.code}</strong></td>
                        <td style="padding:8px; text-align:right; border-bottom:1px solid rgb(var(--border)); color:rgb(var(--text));">${item.qty}</td>
                        <td style="padding:8px; text-align:right; border-bottom:1px solid rgb(var(--border)); color:rgb(var(--text));">${(item.sell_price || 0).toLocaleString()}đ</td>
                        <td style="padding:8px; text-align:right; border-bottom:1px solid rgb(var(--border)); color:rgb(var(--text));">${item.has_cost ? (item.cost_price || 0).toLocaleString() + 'đ' : '<span style="color:rgb(var(--warning))">?</span>'}</td>
                        <td style="padding:8px; text-align:right; border-bottom:1px solid rgb(var(--border)); color:rgb(var(--text));">${itemRevenue.toLocaleString()}đ</td>
                        <td style="padding:8px; text-align:right; border-bottom:1px solid rgb(var(--border)); color:rgb(var(--text));">${item.has_cost ? itemCost.toLocaleString() + 'đ' : '-'}</td>
                        <td style="padding:8px; text-align:right; border-bottom:1px solid rgb(var(--border)); ${profitClass}">${item.has_cost ? itemProfit.toLocaleString() + 'đ' : '<span style="color:rgb(var(--warning))">0đ</span>'}</td>
                        <td style="padding:8px; text-align:right; border-bottom:1px solid rgb(var(--border)); ${profitClass}">${item.has_cost ? itemMargin + '%' : '-'}</td>
                    </tr>`;
            });

            itemsHtml += '</tbody></table>';
        }
        
        const profitColor = profit > 0 ? 'rgb(var(--positive))' : (profit < 0 ? 'rgb(var(--negative))' : 'rgb(var(--text))');

        // Build fee display if any fees exist
        let feesHtml = '';
        if (fees && (fees.vat || fees.pvc || fees.discount)) {
            feesHtml = '<div style="margin-top:12px; padding:12px; background:rgb(var(--warning-bg)); border-radius:8px; font-size:13px; color:rgb(var(--text));">';
            feesHtml += '<strong>📊 Phí & Thuế:</strong> ';
            if (fees.vat) feesHtml += `<span style="margin-left:8px;">VAT: +${fees.vat.toLocaleString()}đ</span>`;
            if (fees.pvc) feesHtml += `<span style="margin-left:8px;">Ship: +${fees.pvc.toLocaleString()}đ</span>`;
            if (fees.discount) feesHtml += `<span style="margin-left:8px;">Giảm: -${fees.discount.toLocaleString()}đ</span>`;
            feesHtml += '<br><span style="color:rgb(var(--text-muted));">Đã cộng vào doanh thu và lợi nhuận</span>';
            feesHtml += '</div>';
        }

        document.getElementById('modal-content').innerHTML = `
            <div style="margin-bottom:12px; color:rgb(var(--text));">
                <p><strong>Khách hàng:</strong> ${customer || 'N/A'}</p>
                <p><strong>Ngày:</strong> ${date || 'N/A'}</p>
                <p><a href="tg://privatepost?channel=2124542200&post=${threadId}" target="_blank" style="color:rgb(var(--accent));">Mở trong Telegram →</a></p>
            </div>

            <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:6px; margin-bottom:12px;">
                <div style="background:rgb(var(--surface-hover)); padding:10px; border-radius:5px; text-align:center;">
                    <div style="font-size:11px; color:rgb(var(--text-muted));">Doanh thu</div>
                    <div style="font-size:16px; font-weight:bold; color:rgb(var(--text-heading));">${revenue.toLocaleString()}đ</div>
                </div>
                <div style="background:rgb(var(--surface-hover)); padding:10px; border-radius:5px; text-align:center;">
                    <div style="font-size:11px; color:rgb(var(--text-muted));">Giá vốn</div>
                    <div style="font-size:16px; font-weight:bold; color:rgb(var(--text-heading));">${hasCost ? cost.toLocaleString() + 'đ' : '?'}</div>
                </div>
                <div style="background:rgb(var(--surface-hover)); padding:10px; border-radius:5px; text-align:center;">
                    <div style="font-size:11px; color:rgb(var(--text-muted));">Lợi nhuận</div>
                    <div style="font-size:16px; font-weight:bold; color:${profitColor};">${hasCost ? profit.toLocaleString() + 'đ' : '?'}</div>
                </div>
                <div style="background:rgb(var(--surface-hover)); padding:10px; border-radius:5px; text-align:center;">
                    <div style="font-size:11px; color:rgb(var(--text-muted));">Biên LN</div>
                    <div style="font-size:16px; font-weight:bold; color:${profitColor};">${hasCost ? margin + '%' : '?'}</div>
                </div>
            </div>
            
            <h3 style="margin:10px 0 6px;">Chi tiết sản phẩm</h3>
            ${feesHtml}
            ${itemsHtml}
        `;
        
        document.getElementById('orderModal').style.display = 'block';
        document.body.style.overflow = 'hidden';
    }
    
    function closeModal() {
        document.getElementById('orderModal').style.display = 'none';
        document.body.style.overflow = '';
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
        
        fetch(`/loi-nhuan/api/orders?${params.toString()}`)
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
                        const chips = od.items.map(item => {
                            const cls = item.has_cost ? 'prod-chip ok' : 'prod-chip warn';
                            return `<span class="${cls}"><span class="code">${item.code}</span><span class="qty">×${item.qty}</span></span>`;
                        }).join('');
                        productsHtml = `<div class="prod-chips">${chips}</div>`;
                    }
                    
                    const row = document.createElement('tr');
                    row.style.cursor = 'pointer';
                    row.innerHTML = `
                        <td><a href="tg://privatepost?channel=2124542200&post=${od.thread_id}" target="_blank" onclick="event.stopPropagation()">#${od.thread_id}</a></td>
                        <td>${od.date}</td>
                        <td>${od.customer}${od.order_text ? `<br><small style="color:rgb(var(--text-faint)); font-size:10px; line-height:1.2;">${od.order_text}</small>` : ''}</td>
                        <td>${productsHtml}</td>
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
    """ + _get_preset_highlight_js() + """
    </script>
    """ + bottom_nav + """
</body>
</html>"""

    # Replace chart data placeholder
    html = html.replace('__CHART_DATA__', chart_data)
    return html
