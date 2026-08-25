"""Order detail page generator: generate_order_detail_html."""
from __future__ import annotations
import io
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

from order_db import get_order_by_thread_id
from product_db import calculate_order_profit
from bot_core.config import USER_NAMES

from profit_dashboard.utils import _format_money, _page_head, _nav_html, resolve_customer_name


def generate_order_detail_html(db_conn, thread_id):
    """Generate order detail page."""
    from order_db import get_order_by_thread_id
    
    order = get_order_by_thread_id(db_conn, thread_id)
    if not order:
        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Không tìm thấy</title>
<style>body{{font-family:sans-serif;padding:12px;background:#0f0f14;color:#b4b4be}}a{{color:#60a5fa}}</style></head>
<body>
<h1>❌ Không tìm thấy đơn hàng #{thread_id}</h1>
<p><a href="/loi-nhuan/">← Quay lại Dashboard</a></p>
</body></html>"""
    
    vn_tz = timezone(timedelta(hours=7))
    
    # Get customer
    customer = resolve_customer_name(db_conn, order) or "Khách lẻ"
    
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
    
    top_nav, bottom_nav = _nav_html(
        'dashboard',
        breadcrumbs=[('Dashboard', '/loi-nhuan/'), ('Đơn hàng', None), (f'#{thread_id}', None)],
    )

    extra_css = """
        .container { max-width: 1000px; }
        .info-card { border-radius: 8px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 10px; background: rgb(var(--surface)); }
        .info-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid rgb(var(--border)); }
        .info-row:last-child { border-bottom: 0; }
        .info-label { font-weight: 500; color: rgb(var(--text-muted)); }
        .info-value { font-weight: 600; color: rgb(var(--text-heading)); }
        .info-value a { color: rgb(var(--accent)); }
        .fees-section { padding: 8px 12px; border-radius: 5px; margin-bottom: 10px; background: rgb(var(--warning-bg)); border-left: 3px solid rgb(var(--warning)); }
        .fees-section h3 { margin-bottom: 6px; font-size: 13px; color: rgb(var(--warning-text)); }
        .fees-row { display: flex; justify-content: space-between; padding: 2px 0; font-size: 12px; color: rgb(var(--text)); }
        .tasks-section { border-radius: 8px; padding: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 10px; background: rgb(var(--surface)); }
        .tasks-section h3 { margin-bottom: 8px; font-size: 13px; color: rgb(var(--text-heading)); }
        .task-item { display: flex; align-items: center; gap: 8px; padding: 6px; border-radius: 4px; margin-bottom: 4px; transition: all 0.2s; }
        .task-item:hover { background: rgb(var(--surface-hover)); }
        .task-item.task-done { background: rgb(var(--tag-green-bg)); border-left: 3px solid rgb(var(--positive)); }
        .task-item.task-skip { background: rgb(var(--surface-hover)); border-left: 3px solid rgb(var(--text-faint)); opacity: 0.7; }
        .task-item.task-pending { background: rgb(var(--warning-bg)); border-left: 3px solid rgb(var(--warning)); }
        .task-icon { font-size: 16px; width: 26px; text-align: center; }
        .task-content { flex: 1; }
        .task-name { font-weight: 600; font-size: 13px; margin-bottom: 1px; color: rgb(var(--text-heading)); }
        .task-details { display: flex; gap: 8px; font-size: 11px; color: rgb(var(--text-muted)); }
        .task-by { font-weight: 500; }
        .task-time { color: rgb(var(--text-faint)); }
        .order-summary { border-radius: 8px; padding: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 16px; background: rgb(var(--surface)); }
        .order-summary h3 { margin-bottom: 8px; font-size: 14px; color: rgb(var(--text-heading)); }
        .order-summary-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid rgb(var(--border)); color: rgb(var(--text)); }
        .order-summary-row:last-child { border-bottom: 0; }
        @media (max-width: 768px) {
            .info-row { flex-direction: column; gap: 2px; }
        }
    """

    html = _page_head(f"Đơn hàng #{thread_id}", extra_css=extra_css)
    html += f"""
<body>
    <div class="container">
        {top_nav}
        
        <div class="info-card">
            <div class="info-row">
                <span class="info-label">👤 Khách hàng:</span>
                <span class="info-value">{customer if customer == "Khách lẻ" else f'<a href="/loi-nhuan/customer/{quote(customer)}">{customer}</a>'}</span>
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
            {tasks_html if tasks_html else '<div style="color: rgb(var(--text-faint)); font-size: 13px; padding: 10px;">Chưa có thông tin tiến độ</div>'}
        </div>
        
        {f'''
        <div class="fees-section">
            <h3>💰 Phí & Chiết khấu</h3>
            {f'''
            <div class="fees-row">
                <span>📊 VAT (thuế):</span>
                <strong style="color: rgb(var(--negative));">+{_format_money(vat)}đ</strong>
            </div>''' if vat else ''}
            {f'''
            <div class="fees-row">
                <span>🚚 Phí vận chuyển:</span>
                <strong style="color: rgb(var(--negative));">+{_format_money(pvc)}đ</strong>
            </div>''' if pvc else ''}
            {f'''
            <div class="fees-row">
                <span>🏷️ Chiết khấu:</span>
                <strong style="color: rgb(var(--positive));">-{_format_money(discount)}đ</strong>
            </div>''' if discount else ''}
            {f'''
            <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid rgb(var(--warning)); font-size: 12px; color: rgb(var(--warning-text));">
                ℹ️ Các khoản phí đã được cộng vào doanh thu và lợi nhuận
            </div>''' if (vat or pvc or discount) else ''}
        </div>
        ''' if (vat or pvc or discount or extra_fees) else ''}
        
        <h2 style="margin-bottom: 12px; font-size: 16px; color: rgb(var(--text-heading));">🛒 Sản phẩm ({len(items)})</h2>
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
            
            profit_display = f'{_format_money(item_profit)}đ' if has_cost else '<span style="color: rgb(var(--warning));">?</span>'
            cost_display = f'{_format_money(item.get("cost_price", 0))}đ' if has_cost else '<span style="color: rgb(var(--warning));">?</span>'
            
            html += f"""
                <tr>
                    <td><a href="/loi-nhuan/product/{item['code']}" style="color: rgb(var(--accent)); text-decoration: none;"><strong>{item['code']}</strong></a></td>
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
                <tr><td colspan="8" style="text-align: center; padding: 12px; color: rgb(var(--text-faint));">Không có sản phẩm</td></tr>"""
    
    html += f"""
            </tbody>
        </table>
        </div>
        
        <div class="order-summary">
            <h3>📊 Tổng kết</h3>
            <div class="order-summary-row">
                <span>Tổng số sản phẩm:</span>
                <strong>{sum(item['qty'] for item in items)}</strong>
            </div>
            <div class="order-summary-row">
                <span>Số mã SP khác nhau:</span>
                <strong>{len(items)}</strong>
            </div>
            <div class="order-summary-row">
                <span>Doanh thu:</span>
                <strong>{_format_money(total_revenue)}đ</strong>
            </div>
            <div class="order-summary-row">
                <span>Giá vốn:</span>
                <strong>{_format_money(total_cost)}đ</strong>
            </div>
            <div class="order-summary-row" style="border-bottom: 0; padding-top: 8px; margin-top: 4px; border-top: 2px solid rgb(var(--text-heading));">
                <span style="font-weight: bold; font-size: 15px;">Lợi nhuận:</span>
                <strong style="color: {'rgb(var(--positive))' if total_profit >= 0 else 'rgb(var(--negative))'}; font-size: 15px;">{_format_money(total_profit)}đ</strong>
            </div>
        </div>
        </div>
    </div>
    {bottom_nav}
</body>
</html>"""
    
    return html

