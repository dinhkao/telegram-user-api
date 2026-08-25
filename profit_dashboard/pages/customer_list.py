"""Customer profit list page generator: generate_customer_profit_html."""
from __future__ import annotations
import io
import json
from datetime import datetime, timezone, timedelta

from product_db import calculate_order_profit

from urllib.parse import quote

from profit_dashboard.utils import _format_money, _get_preset_highlight_js, _page_head, _nav_html, _get_date_presets_html, _set_date_preset_js, resolve_customer_name


def generate_customer_profit_html(db_conn, since_date=None, until_date=None):
    """Generate customer profit analysis page."""
    if since_date is None:
        since_date = datetime.now().strftime("%Y-%m-%d")
    
    cur = db_conn.execute(
        "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL "
        "AND json IS NOT NULL AND thread_id >= 460000 "
        "ORDER BY thread_id DESC LIMIT 2000"
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
        
        customer = resolve_customer_name(db_conn, order) or "Khách lẻ"
        
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
    
    top_nav, bottom_nav = _nav_html('customers')

    html = _page_head("Phân tích lợi nhuận theo khách hàng")
    html += f"""
<body>
    <div class="container">
        {top_nav}
        <h1>👥 Phân tích lợi nhuận theo khách hàng</h1>

        <div class="filters">
            {_get_date_presets_html()}
            <form method="GET" action="/loi-nhuan/customers">
                <input type="date" name="since" id="since" value="{since_date or datetime.now().strftime('%Y-%m-%d')}" title="Từ ngày">
                <input type="date" name="until" id="until" value="{until_date or ''}" title="Đến ngày">
                <button type="submit">🔍 Lọc</button>
                <a href="/loi-nhuan/customers" style="padding: 8px 12px; text-decoration: none; color: #3b82f6;">Xóa bộ lọc</a>
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
                    <td><a href="/loi-nhuan/customer/{quote(customer)}" style="color: rgb(var(--accent)); text-decoration: none;"><strong>{customer[:40]}</strong></a></td>
                    <td>{data['orders']}</td>
                    <td>{len(data['products'])}</td>
                    <td>{_format_money(data['revenue'])}đ</td>
                    <td>{_format_money(data['cost'])}đ</td>
                    <td class="profit {profit_class}">{profit_display}</td>
                    <td>{margin:.1f}%</td>
                </tr>"""
    
    html += f"""
            </tbody>
        </table>
        </div>
    </div>
    {bottom_nav}
    <script>
    {_set_date_preset_js('.filters form')}
    {_get_preset_highlight_js()}
    </script>
</body>
</html>"""
    
    return html

