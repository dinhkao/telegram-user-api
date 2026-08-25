"""Product detail page generator: generate_product_detail_html."""
from __future__ import annotations
import io
import json
from datetime import datetime, timezone, timedelta

from product_db import get_product

from profit_dashboard.utils import _format_money, _get_date_presets_html, _get_preset_highlight_js, _page_head, _nav_html, _set_date_preset_js, resolve_customer_name


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
        "AND json IS NOT NULL AND thread_id >= 460000 "
        "ORDER BY thread_id DESC LIMIT 2000"
    )
    
    if since_date is None:
        since_date = datetime.now().strftime("%Y-%m-%d")
    
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
                
                customer = resolve_customer_name(db_conn, order)
                
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
    
    top_nav, bottom_nav = _nav_html(
        'dashboard',
        breadcrumbs=[('Dashboard', '/loi-nhuan/'), ('Sản phẩm', None), (product_code, None)],
    )

    extra_css = """
        .product-info { border-radius: 8px; padding: 10px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); background: rgb(var(--surface)); }
        .form { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
        .form input, .form button { padding: 6px; border: 1px solid rgb(var(--border)); border-radius: 4px; font-size: 12px; background: rgb(var(--surface)); color: rgb(var(--text)); }
        .form button { background: rgb(var(--accent)); color: white; cursor: pointer; border: none; }
        .form button:hover { background: rgb(var(--accent-hover)); }
        .form label { color: rgb(var(--text-heading)); }
        @media (max-width: 768px) {
            .form { flex-direction: column; align-items: stretch; }
        }
    """

    html = _page_head(f"Chi tiết sản phẩm {product_code}", extra_css=extra_css)
    html += f"""
<body>
    <div class="container">
        {top_nav}
        <h1>📦 Sản phẩm: {product_code}</h1>
        
        <div class="filter-bar">
            {_get_date_presets_html()}
            <form method="GET" action="/loi-nhuan/product/{product_code}" style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center; width: 100%;">
                <input type="date" name="since" value="{since_date or datetime.now().strftime('%Y-%m-%d')}" title="Từ ngày" onchange="this.form.submit()">
                <input type="date" name="until" value="{until_date or ''}" title="Đến ngày" onchange="this.form.submit()">
                <button type="submit">🔍 Lọc</button>
                <a href="/loi-nhuan/product/{product_code}" style="padding: 8px 12px; text-decoration: none; color: rgb(var(--accent));">Xóa bộ lọc</a>
            </form>
        </div>
        
        <div class="product-info">
            <form method="POST" action="/loi-nhuan/product/{product_code}/cost" class="form">
                <label>Giá vốn: </label>
                <input type="number" name="cost_price" value="{product['cost_price']}" placeholder="Giá vốn">
                <button type="submit">💾 Cập nhật</button>
                {f'<span style="color: rgb(var(--negative)); margin-left: 10px;">⚠️ Chưa có giá vốn - lợi nhuận sẽ = 0</span>' if product['cost_price'] == 0 else ''}
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
                <tr onclick="location.href='/loi-nhuan/order/{od['thread_id']}'" style="cursor: pointer;">
                    <td><a href="/loi-nhuan/order/{od['thread_id']}" style="color: rgb(var(--accent)); text-decoration: none;" onclick="event.stopPropagation()"><strong>#{od['thread_id']}</strong></a></td>
                    <td>{cust_name}</td>
                    <td>{od['qty']}</td>
                    <td>{_format_money(od['sell_price'])}đ</td>
                    <td>{_format_money(od['revenue'])}đ</td>
                    <td>{_format_money(od['cost'])}đ</td>
                    <td class="profit {profit_class}">{_format_money(od['profit'])}đ</td>
                </tr>"""
    
    html += f"""
            </tbody>
        </table>
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


