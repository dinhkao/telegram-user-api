"""Customer detail page generator: generate_customer_detail_html."""
from __future__ import annotations
import io
import json
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

from product_db import calculate_order_profit

from profit_dashboard.utils import _format_money, _get_date_presets_html, _get_preset_highlight_js, _page_head, _nav_html, _set_date_preset_js, resolve_customer_name


def generate_customer_detail_html(db_conn, customer_name, filter_product=None, since_date=None, until_date=None, limit=2000):
    """Generate customer detail page with all orders."""
    vn_tz = timezone(timedelta(hours=7))
    
    # Default date range
    if since_date is None:
        since_date = datetime.now().strftime("%Y-%m-%d")
    
    # Get all orders
    cur = db_conn.execute(
        "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL "
        "AND json IS NOT NULL AND thread_id >= 460000 "
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
        customer = resolve_customer_name(db_conn, order) or "Khách lẻ"
        
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
    
    top_nav, bottom_nav = _nav_html(
        'customers',
        breadcrumbs=[('Dashboard', '/loi-nhuan/'), ('Khách hàng', '/loi-nhuan/customers'), (customer_name, None)],
    )

    extra_css = """
        .items-summary { font-size: 11px; color: rgb(var(--text-muted)); }
    """

    html = _page_head(f"Khách hàng: {customer_name}", extra_css=extra_css)

    html += f"""
<body>
    <div class="container">
        {top_nav}
        <h1>👤 {customer_name}</h1>
        <div class="subtitle">Chi tiết đơn hàng và lịch sử mua hàng</div>
        
        <div class="filter-bar">
            {_get_date_presets_html()}
            <form method="GET" action="/loi-nhuan/customer/{customer_encoded}" style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; width: 100%;">
                <input type="date" name="since" value="{since_date or datetime.now().strftime('%Y-%m-%d')}" title="Từ ngày" onchange="this.form.submit()">
                <input type="date" name="until" value="{until_date or ''}" title="Đến ngày" onchange="this.form.submit()">
                <input type="text" name="product" placeholder="Lọc theo mã SP" value="{filter_product or ''}">
                <button type="submit">🔍 Lọc</button>
                <a href="/loi-nhuan/customer/{customer_encoded}" style="padding: 8px 12px; text-decoration: none; color: rgb(var(--accent));">Xóa bộ lọc</a>
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
                        <td><a href="/loi-nhuan/product/{code}" style="color: rgb(var(--accent)); text-decoration: none;"><strong>{code}</strong></a></td>
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
                    <tr onclick="location.href='/loi-nhuan/order/{od['thread_id']}'" style="cursor: pointer;">
                        <td><a href="/loi-nhuan/order/{od['thread_id']}" style="color: rgb(var(--accent)); text-decoration: none;" onclick="event.stopPropagation()"><strong>#{od['thread_id']}</strong></a> <a href="tg://privatepost?channel=2124542200&post={od['thread_id']}" target="_blank" onclick="event.stopPropagation()" style="color: #999; font-size: 11px;">📱</a></td>
                        <td>{od['date_display']}</td>
                        <td class="items-summary">{products_html}</td>
                        <td>{_format_money(od['revenue'])}đ</td>
                        <td>{_format_money(od['cost'])}đ</td>
                        <td class="profit {profit_class}">{profit_display}</td>
                    </tr>"""
    else:
        html += """
                    <tr><td colspan="6" class="empty-state">Chưa có đơn hàng nào trong kỳ này</td></tr>"""
    
    html += f"""
                </tbody>
            </table>
            </div>
        </div>
    </div>
    {bottom_nav}
    <script>
    {_set_date_preset_js('.filter-bar form')}
    {_get_preset_highlight_js()}
    </script>
</body>
</html>"""
    
    return html

