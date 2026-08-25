"""Pure helpers: money formatting, date presets, loan proration, shared UI components."""
from __future__ import annotations
import calendar
import json

from profit_dashboard.settings import DEFAULT_WEIGHTS


# Cache of customers.firebase_key -> name, keyed by id(db_conn).
# Names change rarely and legacy orders only reference existing customers,
# so a per-connection cache is safe for the long-lived aiohttp app.
_CUSTOMER_NAME_MAP_CACHE = {}


def _customer_name_map(db_conn):
    """Build/return {firebase_key(str): name} for all customers on this conn."""
    cache_key = id(db_conn)
    cached = _CUSTOMER_NAME_MAP_CACHE.get(cache_key)
    if cached is not None:
        return cached
    m = {}
    try:
        cur = db_conn.execute(
            "SELECT firebase_key, json FROM customers WHERE deleted_at IS NULL"
        )
        for fk, j in cur.fetchall():
            try:
                name = (json.loads(j) or {}).get("name")
            except Exception:
                name = None
            if name:
                m[str(fk)] = str(name)
    except Exception:
        pass
    _CUSTOMER_NAME_MAP_CACHE[cache_key] = m
    return m


def resolve_customer_name(db_conn, order):
    """Display name for an order's customer.

    Prefers the order's own denormalized ``customer_name``/``khach_hang`` field;
    for older orders that never stored it, falls back to the customers table via
    ``khach_hang_id`` (which equals customers.firebase_key). Returns "" if unknown.
    """
    customer = order.get("customer_name") or order.get("khach_hang") or ""
    if isinstance(customer, dict):
        customer = customer.get("name", "")
    customer = str(customer or "").strip()
    if customer:
        return customer
    kh_id = order.get("khach_hang_id")
    if kh_id not in (None, ""):
        return _customer_name_map(db_conn).get(str(kh_id), "")
    return ""


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
                </div>"""


def _get_preset_highlight_js():
    """Return JS to highlight the active date preset button on page load."""
    return """
    document.addEventListener('DOMContentLoaded', function() {
        // Highlight matching preset button on load
        const _sinceEl = document.getElementById('since') || document.querySelector('input[name="since"]');
        const _untilEl = document.getElementById('until') || document.querySelector('input[name="until"]');
        if (_sinceEl && _untilEl) {
            const _since = _sinceEl.value;
            const _until = _untilEl.value;
            const _now = new Date();
            const _fmt = d => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
            const _presets = {
                'today':        [_fmt(_now), _fmt(_now)],
                'yesterday':    [_fmt(new Date(_now - 86400000)), _fmt(new Date(_now - 86400000))],
                'last_month':   [_fmt(new Date(_now.getFullYear(), _now.getMonth() - 1, 1)), _fmt(new Date(_now.getFullYear(), _now.getMonth(), 0))]
            };
            for (let m = 0; m < 12; m++) {
                _presets['month_' + (m + 1)] = [_fmt(new Date(_now.getFullYear(), m, 1)), _fmt(new Date(_now.getFullYear(), m + 1, 0))];
            }
            const _partials = {
                '7days':        _fmt(new Date(_now - 7 * 86400000)),
                '14days':       _fmt(new Date(_now - 14 * 86400000)),
                '30days':       _fmt(new Date(_now - 30 * 86400000)),
                'this_week':    _fmt(new Date(_now.getFullYear(), _now.getMonth(), _now.getDate() - _now.getDay() + 1)),
                'this_month':   _fmt(new Date(_now.getFullYear(), _now.getMonth(), 1))
            };
            let _matched = null;
            for (const [p, [s, u]] of Object.entries(_presets)) {
                if (_since === s && _until === u) { _matched = p; break; }
            }
            if (!_matched) {
                for (const [p, s] of Object.entries(_partials)) {
                    if (_since === s && _until === _fmt(_now)) { _matched = p; break; }
                }
            }
            if (_matched) {
                document.querySelectorAll('.presets button').forEach(b => b.classList.remove('active'));
                const _btn = document.querySelector('.presets button[onclick*="' + _matched + '"]');
                if (_btn) _btn.classList.add('active');
            }
        }
    });"""


# ── Dark mode theme system ────────────────────────────────────────────

def _theme_css_tokens():
    """CSS custom properties for light/dark color tokens. Goes in <style>."""
    return """
        :root {
            --bg: 248 250 252;            /* neutral-50 */
            --surface: 255 255 255;        /* white */
            --surface-hover: 241 245 249;  /* neutral-100 */
            --surface-2: 244 244 245;      /* neutral-200 */
            --border: 244 244 245;         /* neutral-100 */
            --text: 63 63 70;              /* neutral-700 */
            --text-heading: 38 38 38;      /* neutral-800 */
            --text-muted: 115 115 115;     /* neutral-500 */
            --text-faint: 163 163 163;     /* neutral-400 */
            --accent: 59 130 246;          /* blue-500 */
            --accent-hover: 37 99 235;     /* blue-600 */
            --positive: 34 197 94;         /* green-500 */
            --negative: 239 68 68;         /* red-500 */
            --warning: 245 158 11;         /* amber-500 */
            --warning-bg: 254 243 199;     /* amber-100 */
            --warning-text: 180 83 9;      /* amber-700 */
            --tag-green-bg: 220 252 231;
            --tag-green-text: 22 101 52;
            --tag-yellow-bg: 254 243 199;
            --tag-yellow-text: 133 77 14;
            --tag-red-bg: 254 226 226;
            --tag-red-text: 153 27 27;
            --chip-ok-bg: 239 246 255;     /* blue-50 */
            --chip-warn-bg: 254 243 199;   /* amber-100 */
        }
        html.dark {
            --bg: 15 15 20;
            --surface: 24 24 32;
            --surface-hover: 35 35 45;
            --surface-2: 40 40 50;
            --border: 42 42 52;
            --text: 180 180 190;
            --text-heading: 235 235 245;
            --text-muted: 130 130 140;
            --text-faint: 90 90 100;
            --accent: 96 165 250;          /* blue-400 */
            --accent-hover: 147 197 253;   /* blue-300 */
            --positive: 52 211 153;        /* emerald-400 */
            --negative: 248 113 113;       /* red-400 */
            --warning: 251 191 36;         /* amber-400 */
            --warning-bg: 69 42 20;
            --warning-text: 253 224 71;
            --tag-green-bg: 20 50 35;
            --tag-green-text: 134 239 172;
            --tag-yellow-bg: 69 42 20;
            --tag-yellow-text: 253 224 71;
            --tag-red-bg: 60 25 25;
            --tag-red-text: 252 165 165;
            --chip-ok-bg: 30 40 65;
            --chip-warn-bg: 69 42 20;
        }"""


def _theme_init_js():
    """JS to apply saved theme before paint (prevents flash). Goes in <head>."""
    return """
    (function() {
        const t = localStorage.getItem('pd-theme');
        if (t === 'dark') document.documentElement.classList.add('dark');
    })();
    document.addEventListener('DOMContentLoaded', function() {
        const btn = document.getElementById('theme-toggle');
        if (btn) btn.textContent = document.documentElement.classList.contains('dark') ? '☀️' : '🌙';
    });
    function toggleTheme() {
        const html = document.documentElement;
        html.classList.toggle('dark');
        localStorage.setItem('pd-theme', html.classList.contains('dark') ? 'dark' : 'light');
        const btn = document.getElementById('theme-toggle');
        if (btn) btn.textContent = html.classList.contains('dark') ? '☀️' : '🌙';
    }"""


def _theme_toggle_html():
    """Theme toggle button for the nav bar."""
    return '<button id="theme-toggle" type="button" onclick="toggleTheme()" style="padding:6px 10px;border:none;border-radius:5px;cursor:pointer;font-size:13px;background:rgb(var(--surface-2));color:rgb(var(--text-heading));margin-left:auto;">🌙</button>'


# ── Shared UI components ─────────────────────────────────────────────

def _shared_css():
    """Common CSS using custom properties for dark mode on all pages."""
    return _theme_css_tokens() + """
        @layer base {
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 4px; background: rgb(var(--bg)); color: rgb(var(--text)); transition: background 0.2s, color 0.2s; }
        }
        a { color: rgb(var(--accent)); }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { margin-bottom: 8px; font-size: 19px; color: rgb(var(--text-heading)); }
        h2 { color: rgb(var(--text-heading)); }
        .subtitle { font-size: 12px; margin-bottom: 8px; color: rgb(var(--text-muted)); }

        /* ── Nav ── */
        .nav { margin-bottom: 8px; display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
        .nav a { padding: 8px 6px; color: white; text-decoration: none; border-radius: 4px; font-size: 12px; white-space: nowrap; background: rgb(var(--accent)); }
        .nav a:hover { background: rgb(var(--accent-hover)); }
        .nav a.active { filter: brightness(0.85); }

        /* ── Breadcrumbs ── */
        .breadcrumbs { font-size: 12px; margin-bottom: 8px; display: flex; align-items: center; gap: 4px; color: rgb(var(--text-muted)); }
        .breadcrumbs a { color: rgb(var(--accent)); text-decoration: none; }
        .breadcrumbs a:hover { text-decoration: underline; }
        .breadcrumbs .sep { margin: 0 2px; }

        /* ── Cards ── */
        .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 6px; margin-bottom: 12px; }
        .card { border-radius: 8px; padding: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); text-align: center; background: rgb(var(--surface)); }
        .card h3 { font-size: 11px; margin-bottom: 2px; color: rgb(var(--text-muted)); font-weight: 500; }
        .card .value { font-size: 18px; font-weight: 700; color: rgb(var(--text-heading)); }
        .card .value.positive { color: rgb(var(--positive)); }
        .card .value.negative { color: rgb(var(--negative)); }

        /* ── Tables ── */
        .table-wrap { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 12px; background: rgb(var(--surface)); }
        table { width: 100%; min-width: 600px; border-collapse: collapse; }
        th, td { padding: 6px 8px; text-align: left; font-size: 13px; border-bottom: 1px solid rgb(var(--border)); color: rgb(var(--text)); }
        th { font-weight: 600; white-space: nowrap; background: rgb(var(--surface-hover)); color: rgb(var(--text-heading)); }
        tr:hover { background: rgb(var(--surface-hover)); }
        .profit { font-weight: 600; }
        .profit.positive { color: rgb(var(--positive)); }
        .profit.negative { color: rgb(var(--negative)); }
        .text-right { text-align: right; }

        /* ── Filters ── */
        .filters, .filter-bar { border-radius: 8px; padding: 8px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); display: flex; flex-wrap: wrap; align-items: center; gap: 4px; background: rgb(var(--surface)); }
        .filters input, .filters button, .filter-bar input, .filter-bar button { padding: 6px; border-radius: 4px; font-size: 12px; border: 1px solid rgb(var(--border)); background: rgb(var(--surface)); color: rgb(var(--text)); }
        .filters input[type="date"], .filter-bar input[type="date"] { width: auto; min-width: 110px; }
        .filters input[type="text"], .filter-bar input[type="text"] { width: auto; min-width: 90px; }
        .filters button, .filter-bar button { background: rgb(var(--accent)); color: white; cursor: pointer; border: none; }
        .filters button:hover, .filter-bar button:hover { background: rgb(var(--accent-hover)); }
        .filters a, .filter-bar a { padding: 6px; text-decoration: none; white-space: nowrap; font-size: 12px; color: rgb(var(--accent)); }
        .presets { display: flex; flex-wrap: nowrap; overflow-x: auto; gap: 2px; margin-bottom: 6px; width: 100%; }
        .presets button { padding: 2px 6px; border: none; border-radius: 2px; cursor: pointer; font-size: 11px; white-space: nowrap; background: rgb(var(--surface-2)); color: rgb(var(--text)); }
        .presets button:hover { filter: brightness(0.9); }
        .presets button.active { background: rgb(var(--accent)); color: white; }

        /* ── Section ── */
        .section { margin-bottom: 12px; }
        .section h2 { margin-bottom: 6px; font-size: 14px; color: rgb(var(--text-heading)); }

        /* ── Tags ── */
        .tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; }
        .tag.green { background: rgb(var(--tag-green-bg)); color: rgb(var(--tag-green-text)); }
        .tag.red { background: rgb(var(--tag-red-bg)); color: rgb(var(--tag-red-text)); }
        .tag.yellow { background: rgb(var(--tag-yellow-bg)); color: rgb(var(--tag-yellow-text)); }

        /* ── Empty state ── */
        .empty-state { text-align: center; padding: 12px; font-size: 13px; color: rgb(var(--text-faint)); }

        /* ── Bottom nav (mobile) ── */
        .bottom-nav { display: none; position: fixed; bottom: 0; left: 0; right: 0; z-index: 100; padding: 4px 0 max(4px, env(safe-area-inset-bottom)); background: rgb(var(--surface)); border-top: 1px solid rgb(var(--border)); box-shadow: 0 -2px 8px rgba(0,0,0,0.1); }
        .bottom-nav a { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 2px; text-decoration: none; font-size: 10px; padding: 4px 0; color: rgb(var(--text-muted)); transition: color 0.15s; }
        .bottom-nav a .bn-icon { font-size: 18px; }
        .bottom-nav a.active { color: rgb(var(--accent)); }

        /* ── Loading spinner ── */
        .spinner { border: 3px solid rgb(var(--border)); border-top: 3px solid rgb(var(--accent)); border-radius: 50%; width: 20px; height: 20px; animation: pd-spin 1s linear infinite; display: inline-block; margin-right: 10px; }
        @keyframes pd-spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

        /* ── Responsive ── */
        @media (max-width: 768px) {
            body { padding: 4px; padding-bottom: 60px; }
            h1 { font-size: 16px; }
            .summary { grid-template-columns: 1fr 1fr; gap: 4px; }
            .card { padding: 8px; }
            .card h3 { font-size: 10px; }
            .card .value { font-size: 16px; }
            .nav a { font-size: 11px; padding: 4px 6px; }
            .filters, .filter-bar { flex-direction: column; align-items: stretch; }
            .filters input, .filter-bar input { width: 100%; }
            .filters button, .filter-bar button { width: 100%; }
            th, td { padding: 4px 6px; font-size: 12px; }
            .bottom-nav { display: flex; }
        }
        @media (max-width: 480px) {
            .card .value { font-size: 14px; }
            h1 { font-size: 15px; }
        }
    """


def _nav_html(active='dashboard', breadcrumbs=None):
    """Generate unified navigation.

    Returns (top_nav_html, bottom_nav_html) tuple.
    active: 'dashboard' | 'customers' | 'settings' | 'order' | 'customer' | 'product'
    breadcrumbs: list of (label, url) tuples; last item's url is ignored (rendered as text).
    """
    nav_items = [
        ('dashboard', '/loi-nhuan/', '🏠 Dashboard'),
        ('customers', '/loi-nhuan/customers', '👥 Khách hàng'),
        ('settings', '/loi-nhuan/settings', '⚙️ Cấu hình'),
    ]

    links = []
    for key, url, label in nav_items:
        cls = ' class="active"' if active == key else ''
        links.append(f'<a href="{url}"{cls}>{label}</a>')
    links.append(_theme_toggle_html())

    top = '        <div class="nav">\n            ' + '\n            '.join(links) + '\n        </div>'

    if breadcrumbs:
        parts = []
        for i, (label, url) in enumerate(breadcrumbs):
            if i < len(breadcrumbs) - 1:
                parts.append(f'<a href="{url}">{label}</a>')
            else:
                parts.append(f'<span>{label}</span>')
        top += '\n        <nav class="breadcrumbs">' + ' <span class="sep">›</span> '.join(parts) + '</nav>'

    bottom_items = [
        ('dashboard', '/loi-nhuan/', '🏠', 'Home'),
        ('customers', '/loi-nhuan/customers', '👥', 'KH'),
        ('settings', '/loi-nhuan/settings', '⚙️', 'Cài đặt'),
    ]
    bottom_links = []
    for key, url, icon, label in bottom_items:
        cls = ' class="active"' if active == key else ''
        bottom_links.append(f'<a href="{url}"{cls}><span class="bn-icon">{icon}</span><span>{label}</span></a>')
    bottom = '    <nav class="bottom-nav">' + ''.join(bottom_links) + '</nav>'

    return top, bottom


def _page_head(title, extra_css='', chart=False):
    """Generate shared <head> section with theme support.

    Returns the string from <!DOCTYPE html> through the end of </head>.
    """
    scripts = '<script src="https://cdn.tailwindcss.com"></script>\n'
    if chart:
        scripts += '    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>\n'

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    {scripts}    <style>
    {_shared_css()}
    {extra_css}
    </style>
    <script>{_theme_init_js()}</script>
</head>"""


def _set_date_preset_js(form_selector='.filters form'):
    """Shared setDatePreset JS function."""
    return """
    function setDatePreset(preset) {
        const now = new Date();
        const fmt = d => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
        let since, until;
        switch(preset) {
            case 'today': since = until = fmt(now); break;
            case 'yesterday': { const y = new Date(now); y.setDate(y.getDate() - 1); since = until = fmt(y); break; }
            case 'this_week': { const m = new Date(now); m.setDate(m.getDate() - m.getDay() + 1); if (m > now) m.setDate(m.getDate() - 7); since = fmt(m); until = fmt(now); break; }
            case '7days': { const d = new Date(now); d.setDate(d.getDate() - 7); since = fmt(d); until = fmt(now); break; }
            case '14days': { const d = new Date(now); d.setDate(d.getDate() - 14); since = fmt(d); until = fmt(now); break; }
            case '30days': { const d = new Date(now); d.setDate(d.getDate() - 30); since = fmt(d); until = fmt(now); break; }
            case 'this_month': since = fmt(new Date(now.getFullYear(), now.getMonth(), 1)); until = fmt(now); break;
            case 'last_month': { const f = new Date(now.getFullYear(), now.getMonth() - 1, 1); const l = new Date(now.getFullYear(), now.getMonth(), 0); since = fmt(f); until = fmt(l); break; }
            default:
                if (preset.startsWith('month_')) {
                    const m = parseInt(preset.split('_')[1]) - 1;
                    since = fmt(new Date(now.getFullYear(), m, 1));
                    until = fmt(new Date(now.getFullYear(), m + 1, 0));
                }
                break;
        }
        const sinceEl = document.getElementById('since') || document.querySelector('input[name="since"]');
        const untilEl = document.getElementById('until') || document.querySelector('input[name="until"]');
        if (sinceEl) sinceEl.value = since;
        if (untilEl) untilEl.value = until;
        document.querySelectorAll('.presets button').forEach(b => b.classList.remove('active'));
        if (event && event.target) event.target.classList.add('active');
        const form = document.querySelector('""" + form_selector + """');
        if (form) form.submit();
    }
    """
