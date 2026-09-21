"""Tính toán THUẦN cho dashboard lợi nhuận bản NATIVE trong webapp (#/loi-nhuan).

Trả dict JSON-ready cho server_app/profit_api_routes.py; chạy trong thread với
connection riêng (quét full bảng orders). Toàn bộ lịch sử theo ngày giờ VN, gồm phiếu trả đã xác nhận; lợi nhuận từng
đơn = product_store.calculate_order_profit (giá vốn frozen ưu tiên). Kết nối:
order blob (orders), product_store, profit_dashboard.utils (loan proration).
Tests: tests/test_profit_compute.py.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from product_db import calculate_order_profit, get_all_products

from profit_dashboard.queries import MIN_THREAD_ID, _created_vn
from profit_dashboard.utils import calc_prorated_loan, resolve_customer_name
from profit_dashboard.filters import apply_filters


def scan_orders(conn, since: str | None, until: str | None, *, quality=None) -> list[dict]:
    """Toàn lịch sử hợp lệ theo ngày VN + điều chỉnh trả hàng, không cutoff ID."""
    from collections import Counter
    from profit_dashboard.returns import published_returns, scan_returns
    quality = quality if quality is not None else Counter()
    slips = published_returns(conn)
    return_invoice_ids = {str(s['kv_invoice_id']) for s in slips}
    cur = conn.execute("SELECT thread_id, json FROM orders WHERE deleted_at IS NULL "
                       "AND json IS NOT NULL ORDER BY thread_id DESC")
    out, sources, source_days = [], {}, []
    for row in cur.fetchall():
        try:
            order = json.loads(row[1])
            if not isinstance(order, dict):
                raise ValueError('Đơn không hợp lệ')
            sources[row[0]] = order
            invoice = order.get('invoice') or order.get('invoice_items') or []
            if not invoice:
                continue
            # Phiếu trả là nguồn duy nhất cho hóa đơn âm đã được nhập vào orders.
            kv_id = order.get('kiotvietInvoiceID') or order.get('kv_invoice_id') or order.get('kiotviet_invoice_id')
            if kv_id is not None and str(kv_id) in return_invoice_ids and all(
                    float(i.get('price') or 0) < 0 for i in invoice):
                quality['duplicate_return_orders'] += 1
                continue
            ymd, date_display = _created_vn(order.get('created'))
            if not ymd:
                quality['undated_orders'] += 1
                quality.setdefault('undated_order_ids', []).append(row[0])
                continue
            source_days.append(ymd)
            if (since and ymd < since) or (until and ymd > until):
                continue
            res = calculate_order_profit(conn, order)
            if not res['items']:
                continue
            out.append({
                'entry_id': f'order:{row[0]}', 'kind': 'sale', 'thread_id': row[0],
                'customer': str(resolve_customer_name(conn, order) or '') or 'Khách lẻ',
                'has_payment': bool(order.get('payments')), 'ymd': ymd, 'date': date_display,
                'revenue': res['total_revenue'], 'customer_total': res['customer_total'],
                'cost': res['total_cost'], 'profit': res['total_profit'],
                'cost_complete': res['cost_complete'], 'items': res['items'],
                'items_with_cost': res['items_with_cost'], 'fees': res['fees'],
                'shipping_cost_recorded': res['shipping_cost_recorded'],
                'text': str(order.get('text') or '').strip()[:80],
            })
        except (ValueError, TypeError, ArithmeticError):
            quality['invalid_orders'] += 1
            quality.setdefault('invalid_order_ids', []).append(row[0])
    quality['first_order_date'] = min(source_days) if source_days else None
    quality['last_order_date'] = max(source_days) if source_days else None
    out.extend(scan_returns(conn, since, until, sources, slips, quality))
    return out


def _scan_with_quality(conn, since, until):
    from collections import Counter
    coverage = Counter()
    rows = scan_orders(conn, since, until, quality=coverage)
    coverage['quality_errors'] = any(coverage[k] for k in ('invalid_orders', 'undated_orders', 'invalid_returns', 'undated_returns', 'return_amount_mismatches'))
    return rows, dict(coverage)


def _quality(rows):
    items = [it for r in rows for it in r['items']]
    missing = [it for it in items if not it['has_cost']]
    return {'cost_complete': not missing,
            'missing_cost_orders': sum(not r['cost_complete'] for r in rows if r['kind'] == 'sale'),
            'missing_cost_returns': sum(not r['cost_complete'] for r in rows if r['kind'] == 'return'),
            'missing_cost_lines': len(missing),
            'missing_cost_revenue': sum(it['revenue'] for r in rows if r['kind'] == 'sale' for it in r['items'] if not it['has_cost']),
            'uncertain_return_revenue': -sum(it['revenue'] for r in rows if r['kind'] == 'return' for it in r['items'] if not it['has_cost'])}


def _totals(rows):
    return {**{k: sum(r[k] for r in rows) for k in ('revenue', 'cost', 'profit')},
            'orders': sum(r['kind'] == 'sale' for r in rows),
            'returns': sum(r['kind'] == 'return' for r in rows), **_quality(rows)}


def _pct(cur: float, prev: float) -> float | None:
    """% thay đổi theo độ lớn kỳ trước; không chia cho 0 khi kỳ này khác 0."""
    if prev == 0:
        return 0.0 if cur == 0 else None
    return round((cur - prev) / abs(prev) * 100, 1)


def _agg_customers(rows: list[dict]) -> dict[str, dict]:
    m: dict[str, dict] = {}
    for r in rows:
        c = m.setdefault(r["customer"], {"revenue": 0, "cost": 0, "profit": 0,
                                         "orders": 0, "returns": 0, "products": set(), "missing_cost_orders": 0})
        c["revenue"] += r["revenue"]
        c["cost"] += r["cost"]
        c["profit"] += r["profit"]
        c["orders"] += int(r["kind"] == "sale")
        c["returns"] += int(r["kind"] == "return")
        c["missing_cost_orders"] += int(any(not it["has_cost"] for it in r["items"]))
        for it in r["items"]:
            c["products"].add(it["code"])
    return m


def _agg_products(rows: list[dict]) -> dict[str, dict]:
    m: dict[str, dict] = {}
    for r in rows:
        seen = set()
        for it in r["items"]:
            p = m.setdefault(it["code"], {"qty": 0, "revenue": 0, "cost": 0, "profit": 0,
                                             "orders": 0, "returns": 0, "missing_cost_lines": 0})
            p["qty"] += it["qty"]
            p["revenue"] += it["revenue"]
            p["cost"] += it["cost"]
            p["profit"] += it["profit"] or 0
            p["missing_cost_lines"] += int(not it["has_cost"])
            if it["code"] not in seen:
                p["orders"] += int(r["kind"] == "sale")
                p["returns"] += int(r["kind"] == "return")
                seen.add(it["code"])
    return m


def _prev_range(since: str | None, until: str | None) -> tuple[str, str] | None:
    """Kỳ trước = cùng độ dài, lùi sát trước kỳ này."""
    try:
        start = datetime.strptime(since, "%Y-%m-%d").date()
        end = datetime.strptime(until, "%Y-%m-%d").date() if until else datetime.now().date()
        if end < start:
            end = start
        days = (end - start).days + 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=days - 1)
        return prev_start.strftime("%Y-%m-%d"), prev_end.strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError):
        return None


def _loan_for_range(since, until, base_monthly, weights):
    if not since or not until or base_monthly <= 0:
        return 0
    return calc_prorated_loan(datetime.strptime(since, "%Y-%m-%d").date(),
                              datetime.strptime(until, "%Y-%m-%d").date(), base_monthly, weights)


def dashboard_data(conn, since: str | None, until: str | None,
                   yearly_loan: int, weights: dict | None,
                   filter_product: str | None = None,
                   filter_customer: str | None = None,
                   paid_only: bool = False, payment: str = "all",
                   profitability: str = "all", cost_status: str = "all") -> dict:
    from collections import Counter
    from product_store.resolve import resolve_code
    until = until or datetime.now(timezone(timedelta(hours=7))).date().isoformat()
    filter_product = (resolve_code(conn, filter_product) or {}).get('code', filter_product) if filter_product else None
    filters = dict(paid_only=paid_only, payment=payment, profitability=profitability, cost_status=cost_status)
    coverage = Counter()
    all_rows = scan_orders(conn, since, until, quality=coverage)
    rows = apply_filters(all_rows, filter_product, filter_customer, **filters)
    totals = _totals(rows)
    revenue, cost, profit = (totals[k] for k in ('revenue', 'cost', 'profit'))
    sales = [r for r in rows if r['kind'] == 'sale']
    returns = [r for r in rows if r['kind'] == 'return']
    filtered = bool(filter_product or filter_customer or paid_only or any(v != 'all' for v in (payment, profitability, cost_status)))
    base_monthly = (yearly_loan or 0) / 12.0
    company_loan = _loan_for_range(since, until, base_monthly, weights)
    loan = None if filtered else company_loan
    real_profit = profit - loan if loan is not None else None

    prev = _totals([])
    prev_label = ''
    pr = _prev_range(since, until)
    prev_loan = 0
    if pr:
        prev = _totals(apply_filters(scan_orders(conn, *pr), filter_product, filter_customer, **filters))
        prev_label = f"{pr[0][8:10]}/{pr[0][5:7]}/{pr[0][:4]} – {pr[1][8:10]}/{pr[1][5:7]}/{pr[1][:4]}"
        prev_loan = _loan_for_range(*pr, base_monthly, weights)
    prev_real = None if filtered else prev['profit'] - prev_loan
    comparable_profit = totals['cost_complete'] and prev['cost_complete']
    quality_errors = any(coverage[k] for k in ('invalid_orders', 'undated_orders', 'invalid_returns', 'undated_returns', 'return_amount_mismatches'))
    if quality_errors:
        comparable_profit = False
    cust_map, prod_map = _agg_customers(rows), _agg_products(rows)
    product_info = {p['code']: p for p in get_all_products(conn)}
    top_customers = [
        {'name': n, 'revenue': d['revenue'], 'profit': d['profit'], 'orders': d['orders'], 'returns': d['returns'],
         'missing_cost_orders': d['missing_cost_orders'],
         'margin': round(d['profit'] / d['revenue'] * 100, 1) if d['revenue'] > 0 and not d['missing_cost_orders'] else None,
         'revenue_share': round(d['revenue'] / revenue * 100, 1) if revenue > 0 else 0}
        for n, d in sorted(cust_map.items(), key=lambda x: x[1]['profit'], reverse=True)[:5]]
    products = [{
        'code': c, **d,
        'margin': round(d['profit'] / d['revenue'] * 100, 1) if d['revenue'] > 0 and not d['missing_cost_lines'] else None,
        'cost_price': int((product_info.get(c) or {}).get('cost_price') or 0),
        'name': (product_info.get(c) or {}).get('name') or '',
    } for c, d in sorted(prod_map.items(), key=lambda x: x[1]['profit'], reverse=True)]

    daily = {}
    for r in rows:
        d = daily.setdefault(r['ymd'], {'revenue': 0, 'cost': 0, 'profit': 0, 'orders': 0, 'returns': 0, 'cost_complete': True})
        for k in ('revenue', 'cost', 'profit'):
            d[k] += r[k]
        d['orders'] += int(r['kind'] == 'sale')
        d['returns'] += int(r['kind'] == 'return')
        d['cost_complete'] = d['cost_complete'] and r['cost_complete']
    days = sorted(daily)
    if since:
        start = datetime.strptime(since, '%Y-%m-%d').date()
        end = datetime.strptime(until, '%Y-%m-%d').date()
        days = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    chart, allocated = [], 0
    for day in days:
        cumulative = _loan_for_range(since, day, base_monthly, weights)
        dl = cumulative - allocated
        allocated = cumulative
        d = daily.get(day, {'revenue': 0, 'cost': 0, 'profit': 0, 'orders': 0, 'returns': 0, 'cost_complete': True})
        chart.append({'day': day, **d, 'loan': None if filtered else dl,
                      'real_profit': None if filtered else d['profit'] - dl})

    items = [it for r in rows for it in r['items']]
    complete_sales = [r for r in sales if r['cost_complete']]
    loss_rows = [r for r in complete_sales if r['profit'] < 0]
    low_rows = [r for r in complete_sales if r['revenue'] > 0 and 0 <= r['profit'] / r['revenue'] < .1]
    gross_margin = round(profit / revenue * 100, 1) if revenue > 0 and totals['cost_complete'] else None
    prev_margin = round(prev['profit'] / prev['revenue'] * 100, 1) if prev['revenue'] > 0 and prev['cost_complete'] else None
    coverage = dict(coverage)
    coverage.update({'basis': 'all_local_orders_by_created_date_vn', 'quality_errors': quality_errors,
                     'legacy_orders_included': sum(r['thread_id'] < MIN_THREAD_ID for r in sales)})
    return {
        'summary': {
            'cost_basis': 'includes_output_vat_provision',
            **totals, 'entries': len(rows), 'loan': loan, 'company_loan': company_loan, 'real_profit': real_profit,
            'margin': round(real_profit / revenue * 100, 1) if real_profit is not None and revenue > 0 and totals['cost_complete'] else None,
            'gross_margin': gross_margin,
            'margin_change': round(gross_margin - prev_margin, 1) if gross_margin is not None and prev_margin is not None else None,
            'avg_order_revenue': round(sum(r['revenue'] for r in sales) / len(sales)) if sales else 0,
            'avg_order_profit': round(sum(r['profit'] for r in sales) / len(sales)) if sales and all(r['cost_complete'] for r in sales) else None,
            'customers': len(cust_map), 'products': len(prod_map), 'active_days': len(daily), 'period_days': len(days),
            'received_orders': sum(r['has_payment'] for r in sales),
            'unreceived_orders': sum(not r['has_payment'] for r in sales),
            'cost_coverage': round((len(items) - totals['missing_cost_lines']) / len(items) * 100, 1) if items else None,
            'loss_orders': len(loss_rows), 'loss_total': sum(r['profit'] for r in loss_rows), 'low_margin_orders': len(low_rows),
            'fees': {k: sum(r['fees'][k] for r in rows) for k in ('vat', 'pvc', 'discount', 'fee_total', 'shipping_cost')},
            'customer_total': sum(r['customer_total'] for r in rows),
            'sales_revenue': sum(r['revenue'] for r in sales), 'returns_revenue': -sum(r['revenue'] for r in returns),
            'shipping_cost_unrecorded_orders': sum(not r['shipping_cost_recorded'] and r['fees']['pvc'] > 0 for r in sales),
            'filtered': filtered, 'sales_only_filter': bool(paid_only or payment != 'all' or profitability != 'all'),
            'changes': {**{k: _pct(totals[k], prev[k]) if not quality_errors and (k != 'profit' or comparable_profit) else None
                          for k in ('revenue', 'cost', 'profit', 'orders')},
                        'real_profit': _pct(real_profit, prev_real) if real_profit is not None and comparable_profit else None},
            'prev': prev, 'prev_label': prev_label, 'prev_range': {'since': pr[0], 'until': pr[1]} if pr else None,
            'prev_real_profit': prev_real,
        },
        'top_customers': top_customers, 'top_products': products[:5], 'products': products,
        'chart': chart, 'coverage': coverage,
    }


def customers_data(conn, since: str | None, until: str | None) -> dict:
    rows, coverage = _scan_with_quality(conn, since, until)
    m = _agg_customers(rows)
    out = [{"name": n, "revenue": d["revenue"], "cost": d["cost"], "profit": d["profit"],
            "orders": d["orders"], "returns": d["returns"], "missing_cost_orders": d["missing_cost_orders"], "product_count": len(d["products"])}
           for n, d in sorted(m.items(), key=lambda x: x[1]["profit"], reverse=True)]
    return {"customers": out, "totals": _totals(rows), "coverage": coverage}


def customer_detail_data(conn, name: str, since: str | None, until: str | None) -> dict:
    rows, coverage = _scan_with_quality(conn, since, until)
    rows = [r for r in rows
            if r["customer"].lower() == (name or "").lower()]
    prod_map = _agg_products(rows)
    products = [{"code": c, "qty": d["qty"], "revenue": d["revenue"], "profit": d["profit"], "missing_cost_lines": d["missing_cost_lines"]}
                for c, d in sorted(prod_map.items(), key=lambda x: x[1]["profit"], reverse=True)]
    return {"name": name, "orders": rows, "products": products, "totals": _totals(rows), "coverage": coverage}


def product_detail_data(conn, code: str, since: str | None, until: str | None) -> dict:
    code = (code or "").upper().strip()
    from product_store.resolve import resolve_code
    product = resolve_code(conn, code) or {"code": code, "name": "", "cost_price": 0}
    code = product["code"]
    rows, coverage = _scan_with_quality(conn, since, until)
    orders = []
    total = {"qty": 0.0, "revenue": 0, "cost": 0, "profit": 0, "missing_cost_lines": 0, "sales_qty": 0, "sales_revenue": 0}
    for r in rows:
        for it in r["items"]:
            if it["code"] != code:
                continue
            orders.append({"entry_id": r["entry_id"], "kind": r["kind"], "return_id": r.get("return_id"), "thread_id": r["thread_id"], "customer": r["customer"],
                           "date": r["date"], "ymd": r["ymd"], "qty": it["qty"],
                           "sell_price": it["sell_price"], "cost_price": it["cost_price"],
                           "revenue": it["revenue"], "cost": it["cost"],
                           "profit": it["profit"] or 0, "has_cost": it["has_cost"]})
            if r["kind"] == "sale":
                total["sales_qty"] += it["qty"]
                total["sales_revenue"] += it["revenue"]
            total["qty"] += it["qty"]
            total["revenue"] += it["revenue"]
            total["cost"] += it["cost"]
            total["profit"] += it["profit"] or 0
            total["missing_cost_lines"] += int(not it["has_cost"])
    # Gộp cho khối "Báo cáo bán ra" ở trang chi tiết SP: top khách (theo doanh thu,
    # kèm giá bán TB + lần mua gần nhất) + chuỗi theo NGÀY cho biểu đồ
    cust: dict[str, dict] = {}
    daily: dict[str, dict] = {}
    for o in orders:
        c = cust.setdefault(o["customer"], {"qty": 0.0, "revenue": 0, "profit": 0,
                                            "orders": 0, "returns": 0, "seen": set(), "last_ymd": "", "sales_qty": 0, "sales_revenue": 0})
        c["qty"] += o["qty"]
        c["revenue"] += o["revenue"]
        c["profit"] += o["profit"]
        if o["entry_id"] not in c["seen"]:
            c["orders"] += int(o["kind"] == "sale")
            c["returns"] += int(o["kind"] == "return")
            c["seen"].add(o["entry_id"])
        if o["kind"] == "sale":
            c["sales_qty"] += o["qty"]
            c["sales_revenue"] += o["revenue"]
            c["last_ymd"] = max(c["last_ymd"], o["ymd"] or "")
        if o["ymd"]:
            d = daily.setdefault(o["ymd"], {"qty": 0.0, "revenue": 0, "profit": 0})
            d["qty"] += o["qty"]
            d["revenue"] += o["revenue"]
            d["profit"] += o["profit"]
    for c in cust.values():
        c.pop("seen")
        c["avg_price"] = int(round(c["sales_revenue"] / c["sales_qty"])) if c["sales_qty"] else 0
    top_customers = [{"name": n, **d} for n, d in
                     sorted(cust.items(), key=lambda x: x[1]["revenue"], reverse=True)]
    chart = [{"day": d, **daily[d]} for d in sorted(daily.keys())]
    total["customers"] = len(cust)
    total["orders"] = len({o["entry_id"] for o in orders if o["kind"] == "sale"})
    total["returns"] = len({o["entry_id"] for o in orders if o["kind"] == "return"})
    total["cost_complete"] = not total["missing_cost_lines"]
    total["avg_price"] = int(round(total["sales_revenue"] / total["sales_qty"])) if total["sales_qty"] else 0
    prev, changes = _product_prev_period(conn, code, since, until, total)
    return {"product": {"code": code, "name": product.get("name") or "",
                        "cost_price": int(product.get("cost_price") or 0)},
            "orders": orders, "totals": total,
            "top_customers": top_customers, "chart": chart,
            "prev": prev, "changes": {k: None for k in changes} if coverage["quality_errors"] else changes, "coverage": coverage}


def _product_prev_period(conn, code: str, since: str | None, until: str | None,
                         total: dict) -> tuple[dict | None, dict]:
    """KỲ TRƯỚC của 1 SP (cùng độ dài, lùi sát kỳ này — như dashboard): tổng SL /
    doanh thu / số đơn / số khách / giá TB + % thay đổi. None khi khoảng ngày không
    hợp lệ (không có `since`)."""
    pr = _prev_range(since, until)
    if not pr:
        return None, {}
    p = {"qty": 0.0, "revenue": 0, "orders": 0, "since": pr[0], "until": pr[1], "sales_qty": 0, "sales_revenue": 0}
    custs: set[str] = set()
    seen = set()
    for r in scan_orders(conn, pr[0], pr[1]):
        for it in r["items"]:
            if it["code"] != code:
                continue
            p["qty"] += it["qty"]
            p["revenue"] += it["revenue"]
            if r["kind"] == "sale":
                p["sales_qty"] += it["qty"]
                p["sales_revenue"] += it["revenue"]
            if r["kind"] == "sale" and r["entry_id"] not in seen:
                p["orders"] += 1
                seen.add(r["entry_id"])
            custs.add(r["customer"])
    p["customers"] = len(custs)
    p["avg_price"] = int(round(p["sales_revenue"] / p["sales_qty"])) if p["sales_qty"] else 0
    changes = {k: _pct(total[k], p[k]) for k in ("qty", "revenue", "orders", "customers", "avg_price")}
    return p, changes
