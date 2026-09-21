"""Kiểm thử phản ví dụ ngày 10/09: dữ liệu giả, không dùng dữ liệu thật."""
import json
import unittest
from datetime import date
from test_profit_compute import _conn, _add_order
from product_store import upsert_product
from product_store.profit import calculate_order_profit
from profit_dashboard.compute import dashboard_data, product_detail_data, customers_data
from profit_dashboard.queries import orders_feed, _created_vn
from profit_dashboard.utils import calc_prorated_loan


def item(qty=1, price=100, cost=60, **kw):
    return {'sp': 'A', 'sl': qty, 'price': price, 'cost_price': cost, **kw}


class ProfitMathRegressions(unittest.TestCase):
    def setUp(self):
        self.conn = _conn()
        self.conn.execute('CREATE TABLE return_slips (id INTEGER PRIMARY KEY, thread_id INTEGER, customer_key TEXT, items TEXT, total REAL, kv_invoice_id INTEGER, created_at TEXT, deleted_at TEXT, goods_result TEXT)')

    def tearDown(self):
        self.conn.close()

    def sale(self, tid=1, lines=None, day='2026-09-10', **kw):
        _add_order(self.conn, tid, {'created': day+'T03:00:00Z', 'customer_name': 'Test', 'invoice': lines if lines is not None else [item(2)], **kw})

    def ret(self, rid=1, source=1, status='disposed', lines=None, total=100, kv=10, day='2026-09-10', deleted=None):
        lines = lines if lines is not None else [item()]
        goods = {status: [{'sp': i['sp'], 'quantity': i['sl']} for i in lines]} if status else {}
        self.conn.execute('INSERT INTO return_slips VALUES (?,?,?,?,?,?,?,?,?)',
            (rid, source, 'test', json.dumps(lines), total, kv, day+'T01:00:00+07:00', deleted, json.dumps(goods)))

    def report(self, **kw):
        return dashboard_data(self.conn, '2026-09-10', '2026-09-10', 12000000, None, **kw)

    def test_sales_before_legacy_cutoff_and_deleted_order(self):
        self.sale()
        self.sale(2)
        self.conn.execute('UPDATE orders SET deleted_at=1 WHERE thread_id=2')
        self.assertEqual(self.report()['summary']['orders'], 1)
        self.assertEqual(orders_feed(self.conn, 1, 50, '2026-09-10', '2026-09-10', None, None)['total'], 1)

    def test_no_repricing_history_from_current_catalog(self):
        upsert_product(self.conn, 'A', cost_price=60)
        self.sale(lines=[{'sp': 'A', 'sl': 1, 'price': 100}])
        before = self.report()['summary']
        upsert_product(self.conn, 'A', cost_price=99)
        after = self.report()['summary']
        self.assertEqual((before['profit'], after['profit']), (0, 0))
        self.assertEqual(after['missing_cost_revenue'], 100)
        self.assertIsNone(after['gross_margin'])
        self.assertIsNone(after['changes']['profit'])

    def test_zero_cost_requires_explicit_confirmation(self):
        r = calculate_order_profit(None, {'invoice': [item(cost=0, cost_confirmed=True)]})
        self.assertTrue(r['cost_complete'])
        self.assertEqual(r['complete_profit'], 100)
        r = calculate_order_profit(None, {'invoice': [item(cost=0)]})
        self.assertIsNone(r['complete_profit'])
        r = calculate_order_profit(None, {'invoice': [item(cost=60, cost_source='backfill_current')]})
        self.assertIsNone(r['complete_profit'])

    def test_vat_null_fee_shipping_discount_and_customer_total(self):
        r = calculate_order_profit(None, {'invoice': [item()], 'vat': 8, 'pvc': 10, 'discount': 5, 'shipping_cost': 7})
        self.assertEqual((r['total_revenue'], r['customer_total'], r['total_profit']), (105, 113, 46))
        self.assertEqual(calculate_order_profit(None, {'invoice': [item()], 'vat': None})['total_profit'], 40)

    def test_output_vat_already_reserved_in_cost_is_not_deducted_twice(self):
        # Vốn nhập 108 = vốn sản xuất 100 + VAT bán ra dự tính 8.
        # Thu khách 158 = tiền hàng 150 + VAT thực thu 8 => lãi quản trị 50.
        self.sale(lines=[item(price=150, cost=108)], vat=8)
        d = self.report()
        self.assertEqual((d['summary']['revenue'], d['summary']['customer_total'],
                          d['summary']['cost'], d['summary']['profit']), (150, 158, 108, 50))
        self.assertEqual(d['chart'][0]['profit'], 50)
        feed = orders_feed(self.conn, 1, 50, '2026-09-10', '2026-09-10', None, None)['orders'][0]
        self.assertEqual(feed['profit'], 50)
        self.assertEqual(feed['profit'], sum(i['profit'] for i in feed['items']) + feed['fees']['fee_total'])
        self.assertEqual(customers_data(self.conn, '2026-09-10', '2026-09-10')['totals']['profit'], 50)
        # VAT thu thực tế = 0 thì không tự bù VAT ước tính từ giá vốn.
        r = calculate_order_profit(None, {'invoice': [item(price=150, cost=108)], 'vat': 0})
        self.assertEqual(r['total_profit'], 42)

    def test_unknown_line_is_not_breakeven_and_fees_still_apply(self):
        self.sale(lines=[item(), item(cost=None, sp='B')], discount=10)
        s = self.report()['summary']
        self.assertEqual((s['revenue'], s['profit'], s['missing_cost_revenue']), (190, 30, 100))
        self.assertEqual(self.report(profitability='breakeven')['summary']['orders'], 0)
        self.assertIsNone(s['gross_margin'])

    def test_signed_quantity_and_quantity_alias(self):
        r = calculate_order_profit(None, {'invoice': [item(qty=-1)]})
        self.assertEqual((r['total_revenue'], r['total_cost'], r['total_profit']), (-100, -60, -40))
        line = item(2); line['quantity'] = line.pop('sl')
        self.assertEqual(calculate_order_profit(None, {'invoice': [line]})['total_profit'], 80)

    def test_fractional_cost_is_rounded_in_vnd(self):
        r = calculate_order_profit(None, {'invoice': [item(qty=0.3, price=107, cost=63)]})
        self.assertEqual((r['total_revenue'], r['total_cost'], r['total_profit']), (32, 19, 13))

    def test_disposed_return_keeps_sold_cost_and_reduces_profit(self):
        self.sale(); self.ret()
        s = self.report()['summary']
        self.assertEqual((s['revenue'], s['cost'], s['profit'], s['orders'], s['returns']), (100, 120, -20, 1, 1))
        self.assertTrue(s['cost_complete'])

    def test_restock_restores_original_frozen_cost_not_catalog(self):
        self.sale(); upsert_product(self.conn, 'A', cost_price=95)
        self.ret(status='restocked_existing', lines=[{'sp': 'A', 'sl': 1, 'price': 100}])
        s = self.report()['summary']
        self.assertEqual((s['revenue'], s['cost'], s['profit']), (100, 60, 40))
        self.assertTrue(s['cost_complete'])

    def test_restock_without_source_or_snapshot_does_not_guess_cost(self):
        self.sale()
        self.ret(source=None, status='restocked_new', lines=[{'sp': 'A', 'sl': 1, 'price': 100}])
        s = self.report()['summary']
        self.assertEqual((s['profit'], s['missing_cost_returns']), (-20, 1))
        self.assertIsNone(s['gross_margin'])

    def test_pending_goods_do_not_reverse_cost(self):
        self.sale(); self.ret(status=None)
        s = self.report()['summary']
        self.assertEqual((s['revenue'], s['cost'], s['profit']), (100, 120, -20))
        self.assertEqual(s['missing_cost_returns'], 1)

    def test_drafts_deleted_and_duplicate_return_invoices(self):
        self.sale(); self.ret()
        self.ret(rid=2, kv=None); self.ret(rid=3, kv=30, deleted='x'); self.ret(rid=4)
        self.assertEqual(self.report()['summary']['returns'], 1)
        self.assertEqual(self.report()['coverage']['duplicate_return_invoices'], 1)

    def test_negative_order_import_of_same_return_is_not_double_counted(self):
        self.sale(); self.ret()
        self.sale(2, lines=[item(price=-100)], kiotvietInvoiceID=10)
        self.assertEqual(self.report()['summary']['revenue'], 100)

    def test_return_in_later_period_does_not_rewrite_sale_date(self):
        self.sale(day='2026-09-09'); self.ret(status='restocked_existing')
        s = self.report()['summary']
        self.assertEqual((s['orders'], s['returns'], s['revenue'], s['profit']), (0, 1, -100, -40))
        previous = dashboard_data(self.conn, '2026-09-09', '2026-09-09', 0, None)['summary']
        self.assertEqual((previous['revenue'], previous['profit']), (200, 80))

    def test_filtered_groups_have_no_company_interest_deduction(self):
        self.sale()
        for kw in ({'filter_product': 'A'}, {'filter_customer': 'Test'}, {'payment': 'unreceived'}, {'profitability': 'positive'}, {'cost_status': 'complete'}):
            with self.subTest(kw=kw):
                d = self.report(**kw)
                self.assertIsNone(d['summary']['real_profit'])
                self.assertIsNone(d['summary']['loan'])
                self.assertIsNone(d['chart'][0]['real_profit'])
                self.assertGreater(d['summary']['company_loan'], 0)

    def test_return_filter_and_detail_totals_reconcile(self):
        self.sale(); self.ret()
        d = self.report(filter_product='A')
        feed = orders_feed(self.conn, 1, 50, '2026-09-10', '2026-09-10', 'A', None)
        self.assertEqual(d['summary']['revenue'], sum(r['revenue'] for r in feed['orders']))
        self.assertEqual(self.report(payment='unreceived')['summary']['returns'], 0)
        detail = product_detail_data(self.conn, 'A', '2026-09-10', '2026-09-10')
        self.assertEqual((detail['totals']['orders'], detail['totals']['returns']), (1, 1))
        self.assertEqual(customers_data(self.conn, '2026-09-10', '2026-09-10')['totals']['profit'], -20)

    def test_distinct_product_orders_in_current_previous_and_customer(self):
        self.sale(lines=[item(), item(price=110)])
        self.sale(2, lines=[item(), item()], day='2026-09-09')
        d = product_detail_data(self.conn, 'A', '2026-09-10', '2026-09-10')
        self.assertEqual((d['totals']['orders'], d['prev']['orders'], d['top_customers'][0]['orders']), (1, 1, 1))
        self.assertEqual(d['totals']['revenue'], 210)

    def test_renamed_product_keeps_frozen_prices_in_all_views(self):
        upsert_product(self.conn, 'NEW', cost_price=99)
        pid = self.conn.execute("SELECT id FROM products WHERE code='NEW'").fetchone()[0]
        self.sale(lines=[item(sp='OLD', sp_id=pid)])
        d = self.report(filter_product='NEW')
        self.assertEqual(d['summary']['profit'], 40)
        self.assertEqual(orders_feed(self.conn, 1, 50, '2026-09-10', '2026-09-10', 'NEW', None)['total'], 1)
        self.assertEqual(product_detail_data(self.conn, 'NEW', '2026-09-10', '2026-09-10')['totals']['revenue'], 100)

    def test_daily_chart_and_annual_interest_reconcile(self):
        self.sale(); self.ret(status='restocked_existing')
        d = dashboard_data(self.conn, '2026-01-01', '2026-09-10', 810000000, {'1': 3, '12': 3})
        for k in ('revenue', 'cost', 'profit', 'orders', 'returns', 'loan', 'real_profit'):
            self.assertEqual(sum(r[k] for r in d['chart']), d['summary'][k])
        for year in (2024, 2025, 2026):
            self.assertEqual(calc_prorated_loan(date(year, 1, 1), date(year, 12, 31), 810000000/12, {'1': 3, '12': 3}), 810000000)

    def test_invalid_and_undated_data_is_visible(self):
        self.sale()
        _add_order(self.conn, 2, {'invoice': [item()]})
        self.conn.execute("INSERT INTO orders VALUES ('bad', 3, NULL, NULL, 'not-json', 0, NULL)")
        d = self.report()
        self.assertEqual((d['coverage']['invalid_orders'], d['coverage']['undated_orders']), (1, 1))
        self.assertTrue(d['coverage']['quality_errors'])
        self.assertIsNone(d['summary']['changes']['revenue'])

    def test_return_does_not_change_average_sale_price(self):
        self.sale(lines=[item(qty=2, price=100)])
        self.ret(total=80, lines=[item(price=80)])
        d = product_detail_data(self.conn, 'A', '2026-09-10', '2026-09-10')
        self.assertEqual(d['totals']['revenue'], 120)
        self.assertEqual(d['totals']['qty'], 1)
        self.assertEqual(d['totals']['avg_price'], 100)
        self.assertEqual(d['top_customers'][0]['avg_price'], 100)

    def test_ambiguous_historical_cost_is_not_averaged_or_guessed(self):
        self.sale(lines=[item(cost=60), item(cost=80)])
        self.ret(status='restocked_existing', lines=[{'sp': 'A', 'sl': 1, 'price': 100}])
        self.assertEqual(self.report()['summary']['missing_cost_returns'], 1)

    def test_return_amount_mismatch_is_reconciled_and_flagged(self):
        self.sale(); self.ret(total=105)
        d = self.report()
        self.assertEqual(d['summary']['revenue'], 95)
        self.assertEqual(d['coverage']['return_amount_mismatches'], 1)
        self.assertTrue(d['coverage']['quality_errors'])

    def test_return_source_must_belong_to_customer(self):
        from server_app.return_routes import _validated_return_source
        self.sale(khach_hang_id='test')
        self.assertEqual(_validated_return_source(self.conn, 'test', '1'), 1)
        self.assertIsNone(_validated_return_source(self.conn, 'test', None))
        for value in ('1.2', -1, True, 'missing', 999):
            with self.assertRaises(ValueError):
                _validated_return_source(self.conn, 'test', value)
        with self.assertRaises(ValueError):
            _validated_return_source(self.conn, 'different-customer', 1)

    def test_naive_sqlite_timestamp_is_utc(self):
        self.assertEqual(_created_vn('2026-09-09 18:30:00')[0], '2026-09-10')
