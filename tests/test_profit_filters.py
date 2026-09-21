"""Bộ lọc nghiệp vụ phải cho cùng tập đơn ở KPI, top, bảng SP và feed."""
import unittest
from types import SimpleNamespace
from aiohttp import web
from test_profit_compute import _conn, _add_order
from profit_dashboard.compute import dashboard_data, _pct
from profit_dashboard.queries import orders_feed, MIN_THREAD_ID
from server_app.profit_api_routes import _dates, _filters


class ProfitFiltersTest(unittest.TestCase):
    def setUp(self):
        self.conn = _conn()
        # Đơn lãi, lỗ, biên 5%, hoà vốn, thiếu vốn, thiếu vốn một phần.
        for i, (cost, payment) in enumerate([(60, True), (120, False), (95, True), (100, False), (0, False), (60, False)], 1):
            invoice = [{"sp": f"SP{i}", "sl": 1, "price": 100, "cost_price": cost}]
            if i == 6:
                invoice.append({"sp": "UNKNOWN", "sl": 1, "price": 50, "cost_price": 0})
            _add_order(self.conn, MIN_THREAD_ID + i, {
                "created": f"2026-08-20T0{i}:00:00Z", "customer_name": f"Khách {i}",
                "payments": [{"amount": 1}] if payment else [], "invoice": invoice})

    def tearDown(self):
        self.conn.close()

    def dashboard(self, **kw):
        return dashboard_data(self.conn, "2026-08-20", "2026-08-20", 0, None, **kw)

    def feed(self, **kw):
        return orders_feed(self.conn, 1, 50, "2026-08-20", "2026-08-20", None, None, **kw)

    def test_preset_filters_are_consistent_everywhere(self):
        cases = [({"profitability": "loss"}, [2]), ({"profitability": "breakeven"}, [4]),
                 ({"profitability": "low_margin"}, [3, 4]), ({"profitability": "positive"}, [1, 3]),
                 ({"cost_status": "missing"}, [5, 6]), ({"cost_status": "complete"}, [1, 2, 3, 4]),
                 ({"payment": "received"}, [1, 3]), ({"payment": "unreceived"}, [2, 4, 5, 6]),
                 ({"payment": "received", "profitability": "low_margin"}, [3]),
                 ({"profitability": "loss", "cost_status": "missing"}, [])]
        for filters, ids in cases:
            with self.subTest(filters=filters):
                d, feed = self.dashboard(**filters), self.feed(**filters)
                self.assertEqual({o["thread_id"] - MIN_THREAD_ID for o in feed["orders"]}, set(ids))
                self.assertEqual(d["summary"]["orders"], feed["total"])
                self.assertEqual(d["summary"]["revenue"], sum(o["revenue"] for o in feed["orders"]))
                self.assertEqual(d["summary"]["profit"], sum(o["profit"] for o in feed["orders"]))
                self.assertEqual({c["name"] for c in d["top_customers"]}, {f"Khách {i}" for i in ids})
                self.assertEqual(sum(p["profit"] for p in d["products"]), d["summary"]["profit"])

    def test_missing_cost_quality_and_averages(self):
        s = self.dashboard()["summary"]
        self.assertEqual((s["missing_cost_orders"], s["missing_cost_lines"], s["missing_cost_revenue"]), (2, 2, 150))
        self.assertEqual(s["cost_coverage"], 71.4)
        self.assertEqual((s["loss_orders"], s["loss_total"], s["low_margin_orders"]), (1, -20, 2))
        self.assertEqual((s["received_orders"], s["unreceived_orders"]), (2, 4))
        self.assertEqual(s["avg_order_revenue"], round(650 / 6))

    def test_product_filter_keeps_whole_order_and_normalizes_code(self):
        d = self.dashboard(filter_product=" sp6 ")
        f = orders_feed(self.conn, 1, 50, "2026-08-20", "2026-08-20", " sp6 ", None)
        self.assertEqual((d["summary"]["revenue"], f["orders"][0]["revenue"]), (150, 150))
        self.assertEqual({p["code"] for p in d["products"]}, {"SP6", "UNKNOWN"})

    def test_sort_before_pagination_and_unknown_margins_last(self):
        f = orders_feed(self.conn, 1, 1, "2026-08-20", "2026-08-20", None, None, sort="profit_asc")
        self.assertEqual(f["orders"][0]["thread_id"], MIN_THREAD_ID + 2)
        self.assertTrue(f["has_more"])
        margin = self.feed(sort="margin_asc")["orders"]
        self.assertEqual([o["thread_id"] - MIN_THREAD_ID for o in margin[:4]], [2, 4, 3, 1])

    def test_previous_period_uses_same_filters(self):
        for i, cost in [(20, 150), (21, 50)]:
            _add_order(self.conn, MIN_THREAD_ID + i, {"created": "2026-08-19T05:00:00Z",
                "invoice": [{"sp": "PREV", "sl": 1, "price": 100, "cost_price": cost}]})
        s = self.dashboard(profitability="loss")["summary"]
        self.assertEqual((s["prev"]["profit"], s["prev"]["orders"]), (-50, 1))
        self.assertEqual(s["changes"]["profit"], 60.0)

    def test_undated_orders_do_not_leak_into_every_period(self):
        _add_order(self.conn, MIN_THREAD_ID + 40, {"invoice": [{"sp": "NODATE", "sl": 1, "price": 100, "cost_price": 50}]})
        self.assertEqual(self.dashboard()["summary"]["orders"], 6)
        self.assertEqual(self.feed()["total"], 6)

    def test_chart_covers_long_period_and_loan_reconciles(self):
        d = dashboard_data(self.conn, "2026-01-01", "2026-08-31", 12000001, {"1": 2})
        self.assertEqual(len(d["chart"]), 243)
        for key in ("revenue", "cost", "profit", "loan", "real_profit"):
            self.assertAlmostEqual(sum(p[key] for p in d["chart"]), d["summary"][key])
        empty_day = d["chart"][0]
        self.assertEqual(empty_day["orders"], 0)
        self.assertLess(empty_day["real_profit"], 0)

    def test_empty_and_leap_year_period(self):
        d = dashboard_data(self.conn, "2024-02-01", "2024-02-29", 12000000, None)
        self.assertEqual(len(d["chart"]), 29)
        self.assertEqual(d["summary"]["orders"], 0)
        self.assertIsNone(d["summary"]["gross_margin"])
        self.assertIsNone(d["summary"]["cost_coverage"])
        self.assertEqual(sum(p["loan"] for p in d["chart"]), d["summary"]["loan"])

    def test_all_products_are_available_beyond_old_150_limit(self):
        _add_order(self.conn, MIN_THREAD_ID + 99, {"created": "2026-08-20T00:00:00Z", "invoice": [
            {"sp": f"BULK{i}", "sl": 1, "price": 10, "cost_price": 5} for i in range(151)]})
        d = self.dashboard()
        self.assertEqual(len(d["products"]), 158)
        self.assertEqual(d["summary"]["products"], 158)

    def test_negative_and_zero_comparison(self):
        self.assertEqual(_pct(-20, -50), 60)
        self.assertEqual(_pct(-80, -50), -60)
        self.assertEqual(_pct(10, -50), 120)
        self.assertEqual(_pct(0, 0), 0)
        self.assertIsNone(_pct(10, 0))


class ProfitRequestValidationTest(unittest.TestCase):
    def test_invalid_dates_and_oversized_range(self):
        for since, until in [("2026-02-30", "2026-03-01"), ("2026-09-10", "2026-09-09"), ("bad", "2026-09-10"), ("2000-01-01", "2026-01-01")]:
            with self.assertRaises(web.HTTPBadRequest):
                _dates(SimpleNamespace(query={"since": since, "until": until}))
        self.assertEqual(_dates(SimpleNamespace(query={"since": "2024-02-29", "until": "2024-02-29"})), ("2024-02-29", "2024-02-29"))

    def test_invalid_filters_and_defaults(self):
        for key in ("payment", "profitability", "cost_status", "sort"):
            with self.assertRaises(web.HTTPBadRequest):
                _filters(SimpleNamespace(query={key: "invalid"}), with_sort=True)
        self.assertEqual(_filters(SimpleNamespace(query={}), with_sort=True)["sort"], "newest")
