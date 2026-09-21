"""Điều chỉnh trả hàng trong báo cáo; chỉ đọc, không gọi ensure/migration DB.

Phiếu đã gắn hóa đơn KV là nguồn xác nhận. Ngày báo cáo là ngày tạo phiếu
(vì dữ liệu hiện chưa lưu ngày xác nhận riêng). Không đoán vốn theo giá hiện tại.
"""
from __future__ import annotations

import json
from collections import defaultdict

from product_store.profit import calculate_order_profit, money_value, product_identity
from utils.qty import parse_qty
from profit_dashboard.queries import _created_vn
from profit_dashboard.utils import resolve_customer_name


def published_returns(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='return_slips'").fetchone():
        return []
    cur = conn.execute("SELECT * FROM return_slips WHERE deleted_at IS NULL AND kv_invoice_id IS NOT NULL ORDER BY id")
    names = [c[0] for c in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall() if r[names.index('kv_invoice_id')]]


def scan_returns(conn, since, until, orders, slips, quality):
    out, seen = [], set()
    returned_qty = defaultdict(float)
    for slip in slips:
        invoice_id = str(slip['kv_invoice_id'])
        if invoice_id in seen:
            quality['duplicate_return_invoices'] += 1
            continue
        seen.add(invoice_id)
        ymd, date_display = _created_vn(slip.get('created_at'))
        if not ymd:
            quality['undated_returns'] += 1
            continue
        try:
            items = json.loads(slip.get('items') or '[]')
            result = json.loads(slip.get('goods_result') or '{}')
            if not isinstance(items, list) or not items or not isinstance(result, dict):
                raise ValueError('Phiếu trả không hợp lệ')
            source = orders.get(slip.get('thread_id')) or {}
            source_items = calculate_order_profit(conn, source)['items'] if source else []
            # Xác nhận cùng khách; không lấy vốn từ một liên kết đơn sai khách.
            customer_id = source.get('khach_hang_id')
            if customer_id and str(customer_id) != str(slip.get('customer_key')):
                source_items = []
            handled = {}
            for key, status in [('disposed', 'disposed'), ('restocked_existing', 'restocked'), ('restocked_new', 'restocked')]:
                for entry in result.get(key) or []:
                    code, _ = product_identity(conn, entry)
                    handled[(code, status)] = handled.get((code, status), 0) + max(0, parse_qty(entry.get('quantity')))
            computed = []
            for item in items:
                code, pid = product_identity(conn, item)
                qty = parse_qty(item.get('sl') if item.get('sl') not in (None, '') else item.get('quantity'))
                price = money_value(item.get('price'))
                if not code or qty <= 0 or price < 0:
                    raise ValueError('Dòng trả hàng không hợp lệ')
                disposed = min(qty, handled.get((code, 'disposed'), 0))
                handled[(code, 'disposed')] = handled.get((code, 'disposed'), 0) - disposed
                restocked = min(qty - disposed, handled.get((code, 'restocked'), 0))
                handled[(code, 'restocked')] = handled.get((code, 'restocked'), 0) - restocked
                candidates = [i for i in source_items if i['code'] == code and i['sell_price'] == price and i['qty'] > 0]
                costs = {i['cost_price'] for i in candidates if i['has_cost']}
                matched = candidates and all(i['has_cost'] for i in candidates) and len(costs) == 1
                original_qty = sum(i['qty'] for i in candidates)
                qty_key = (slip.get('thread_id'), code, price)
                returned_qty[qty_key] += qty
                matched = matched and returned_qty[qty_key] <= original_qty + 1e-8
                historical_cost = next(iter(costs)) if matched else None
                # Snapshot vốn trên chính phiếu trả cũng hợp lệ nếu có xác nhận.
                if historical_cost is None and item.get('cost_price') is not None:
                    snap = calculate_order_profit(conn, {'invoice': [item]})['items'][0]
                    historical_cost = snap['cost_price'] if snap['has_cost'] else None
                restored = round(restocked * historical_cost) if historical_cost is not None else 0
                complete = abs(disposed + restocked - qty) < 1e-8 and (restocked == 0 or historical_cost is not None)
                amount = round(qty * price)
                computed.append({'code': code, 'product_id': pid, 'original_code': item.get('sp'),
                    'qty': -qty, 'sell_price': price, 'cost_price': historical_cost,
                    'revenue': -amount, 'cost': -restored, 'profit': -amount + restored,
                    'has_cost': complete, 'is_frozen': historical_cost is not None,
                    'disposed_qty': disposed, 'restocked_qty': restocked,
                    'pending_qty': max(0, qty - disposed - restocked)})
            total = money_value(slip.get('total'))
            if total < 0:
                raise ValueError('Tổng phiếu trả âm')
            difference = -total - sum(i['revenue'] for i in computed)
            # Giữ tổng tiền xác nhận; chênh lệch cấp phiếu không tự chia cho sản phẩm.
            in_range = (not since or ymd >= since) and (not until or ymd <= until)
            if not in_range:
                continue
            if difference:
                quality['return_amount_mismatches'] += 1
            complete = all(i['has_cost'] for i in computed)
            profit = sum(i['profit'] for i in computed) + difference
            out.append({'entry_id': f"return:{slip['id']}", 'kind': 'return', 'return_id': slip['id'],
                'thread_id': -int(slip['id']), 'source_thread_id': slip.get('thread_id'),
                'customer': resolve_customer_name(conn, {'khach_hang_id': slip.get('customer_key')}) or
                            resolve_customer_name(conn, source) or 'Khách lẻ',
                'has_payment': False, 'ymd': ymd, 'date': date_display,
                'revenue': -total, 'customer_total': -total, 'cost': sum(i['cost'] for i in computed),
                'profit': profit, 'cost_complete': complete,
                'items': computed, 'items_with_cost': sum(i['has_cost'] for i in computed),
                'fees': {'vat': 0, 'pvc': 0, 'discount': 0, 'fee_total': difference, 'shipping_cost': 0},
                'shipping_cost_recorded': True, 'text': f"Trả hàng {slip.get('kv_invoice_code') or '#' + str(slip['id'])}"})
        except (TypeError, ValueError, ArithmeticError):
            quality['invalid_returns'] += 1
    return out
