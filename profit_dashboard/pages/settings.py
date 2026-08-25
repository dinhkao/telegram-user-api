"""Settings page generator: generate_settings_html."""
from __future__ import annotations
import io
import json

from profit_dashboard.settings import DEFAULT_WEIGHTS
from profit_dashboard.utils import _format_money, _page_head, _nav_html


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

    top_nav, bottom_nav = _nav_html('settings')

    extra_css = """
        .container { max-width: 800px; }
        .settings-card { border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 10px; background: rgb(var(--surface)); }
        .form-group { margin-bottom: 14px; }
        .form-group label { display: block; font-weight: 600; margin-bottom: 6px; font-size: 13px; color: rgb(var(--text-heading)); }
        .form-group input { width: 100%; padding: 8px; border: 2px solid rgb(var(--border)); border-radius: 5px; font-size: 14px; transition: border-color 0.2s; background: rgb(var(--surface)); color: rgb(var(--text)); }
        .form-group input:focus { outline: none; border-color: rgb(var(--accent)); }
        .form-group .help { font-size: 11px; margin-top: 2px; color: rgb(var(--text-muted)); }
        .btn { padding: 8px 16px; color: white; border: none; border-radius: 5px; font-size: 14px; font-weight: 600; cursor: pointer; background: rgb(var(--positive)); }
        .btn:hover { filter: brightness(0.9); }
        .btn-reset { background: rgb(var(--text-muted)); margin-left: 6px; }
        .btn-reset:hover { filter: brightness(0.9); }
        .weight-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 6px; margin-top: 8px; }
        .weight-row { display: flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 5px; border: 1px solid rgb(var(--border)); background: rgb(var(--surface-hover)); }
        .weight-label { font-weight: 600; min-width: 28px; font-size: 13px; color: rgb(var(--text-heading)); }
        .weight-input { width: 60px; padding: 4px 6px; font-size: 13px; text-align: center; border: 2px solid rgb(var(--border)); border-radius: 4px; background: rgb(var(--surface)); color: rgb(var(--text)); }
        .weight-input:focus { outline: none; border-color: rgb(var(--accent)); }
        .weight-amount { font-size: 12px; font-weight: 500; margin-left: auto; white-space: nowrap; color: rgb(var(--accent)); }
        .preview { padding: 12px; border-radius: 5px; margin-top: 14px; border-left: 4px solid rgb(var(--accent)); background: rgb(var(--surface-hover)); }
        .preview h3 { margin-bottom: 6px; font-size: 13px; color: rgb(var(--text-heading)); }
        .preview-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 12px; color: rgb(var(--text)); }
        .preview-row strong { color: rgb(var(--accent)); }
        .alert { padding: 8px 12px; border-radius: 5px; margin-bottom: 10px; font-size: 13px; display: none; }
        .alert.success { background: rgb(var(--tag-green-bg)); color: rgb(var(--tag-green-text)); border: 1px solid rgb(var(--positive)); }
        .alert.error { background: rgb(var(--tag-red-bg)); color: rgb(var(--tag-red-text)); border: 1px solid rgb(var(--negative)); }
        @media (max-width: 768px) {
            .settings-card { padding: 10px; }
            .weight-grid { grid-template-columns: 1fr; }
        }
    """

    html = _page_head("Cấu hình Dashboard", extra_css=extra_css)
    html += f"""
<body>
    <div class="container">
        {top_nav}
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
    {bottom_nav}
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
                const response = await fetch('/loi-nhuan/api/settings', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ yearly_loan_payment: yearly, monthly_weights: weights }})
                }});

                if (response.ok) {{
                    showAlert('✅ Đã lưu cấu hình thành công!', 'success');
                    setTimeout(() => location.href = '/loi-nhuan/', 1500);
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


