"""Kiểm tra toán độc lập, chỉ dùng SQLite trong RAM; không đọc/ghi dữ liệu thật.
Chạy: .venv/bin/python docs/audits/profit_math_checks.py
Exit 1 nếu còn lệch so với tiêu chí ghi dưới từng test; hiện các lỗi đã được sửa.
"""
from pathlib import Path
import sys
import json
import sqlite3
import unittest
from datetime import date
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from product_store import create_products_table, migrate_products_table, upsert_product
from product_store.profit import calculate_order_profit
from profit_dashboard.compute import dashboard_data, product_detail_data, _pct
from profit_dashboard.queries import MIN_THREAD_ID
from profit_dashboard.utils import calc_prorated_loan


def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE orders (thread_id INTEGER PRIMARY KEY, json TEXT, deleted_at INTEGER)")
    create_products_table(conn)
    migrate_products_table(conn)
    return conn


def add(conn, tid, items, day="2026-09-10", **extras):
    order = {"created": f"{day}T03:00:00Z", "invoice": items, "customer_name": "Khách kiểm thử", **extras}
    conn.execute("INSERT INTO orders VALUES (?, ?, NULL)", (tid, json.dumps(order)))


def item(code="A", quantity=1, price=100, cost=60):
    return {"sp": code, "sl": quantity, "price": price, "cost_price": cost}


class AuditMath(unittest.TestCase):
    def test_output_vat_reserved_in_cost_is_not_deducted_twice(self):
        # Vốn nhập 68 = vốn sản xuất 60 + VAT bán ra dự tính 8; thu khách 108 => lãi 40.
        result = calculate_order_profit(None, {"invoice": [item(cost=68)], "vat": 8})
        self.assertEqual(result["total_profit"], 40)

    def test_product_order_count_is_distinct_orders_not_invoice_lines(self):
        conn = db()
        add(conn, MIN_THREAD_ID+1, [item(), item(quantity=2, price=110)])
        result = product_detail_data(conn, "A", "2026-09-10", "2026-09-10")
        self.assertEqual(result["totals"]["qty"], 3)
        self.assertEqual(result["totals"]["orders"], 1)

    def test_product_identity_survives_code_rename(self):
        conn = db()
        upsert_product(conn, "NEW", cost_price=60)
        pid = conn.execute("SELECT id FROM products WHERE code='NEW'").fetchone()[0]
        add(conn, MIN_THREAD_ID+1, [{**item("OLD"), "sp_id": pid}])
        result = product_detail_data(conn, "NEW", "2026-09-10", "2026-09-10")
        self.assertEqual(result["totals"]["revenue"], 100)

    def test_calendar_report_includes_in_range_orders_before_thread_cutoff(self):
        # Tiêu chí của báo cáo đầy đủ theo ngày; code hiện còn giới hạn legacy.
        conn = db()
        add(conn, MIN_THREAD_ID-1, [item()], day="2026-01-10")
        result = dashboard_data(conn, "2026-01-01", "2026-09-10", 0, None)
        self.assertEqual(result["summary"]["revenue"], 100)

    def test_published_disposed_return_reduces_current_period_revenue(self):
        # Trả hàng đã trừ nợ, hàng hủy: giảm DT 100, không hoàn giá vốn vào kho.
        conn = db()
        add(conn, MIN_THREAD_ID+1, [item(quantity=2)])
        conn.execute("CREATE TABLE return_slips (id INTEGER, thread_id INTEGER, customer_key TEXT, items TEXT, total REAL, kv_invoice_id INTEGER, created_at TEXT, deleted_at TEXT, goods_handled_at TEXT, goods_result TEXT)")
        conn.execute("INSERT INTO return_slips VALUES (1, ?, 'test', ?, 100, 10, '2026-09-10T04:00:00+07:00', NULL, '2026-09-10T04:00:00+07:00', ?)",
                     (MIN_THREAD_ID+1, json.dumps([item()]), json.dumps({"disposed": [{"product_code": "A", "quantity": 1}]})))
        result = dashboard_data(conn, "2026-09-10", "2026-09-10", 0, None)
        self.assertEqual(result["summary"]["revenue"], 100)

    def test_signed_quantity_has_consistent_profit(self):
        # Chỉ là phản ví dụ của điều kiện total_cost>0; dữ liệu live chưa có SL âm.
        result = calculate_order_profit(None, {"invoice": [item(quantity=-1)]})
        self.assertEqual(result["total_profit"], -40)

    def test_nullable_optional_fee_does_not_crash_report(self):
        result = calculate_order_profit(None, {"invoice": [item()], "vat": None})
        self.assertEqual(result["total_profit"], 40)

    def test_quantity_alias_supported_like_other_order_totals(self):
        line = item(quantity=2)
        line["quantity"] = line.pop("sl")
        result = calculate_order_profit(None, {"invoice": [line]})
        self.assertEqual(result["total_revenue"], 200)

    def test_loan_allocation_matches_actual_configuration(self):
        weights = {str(m): 3 if m in (1, 12) else 1 for m in range(1, 13)}
        for year in (2024, 2025, 2026):
            self.assertEqual(calc_prorated_loan(date(year,1,1), date(year,12,31), 810_000_000/12, weights), 810_000_000)
        self.assertEqual(calc_prorated_loan(date(2026,9,1), date(2026,9,10), 810_000_000/12, weights), 16_875_000)

    def test_chart_totals_match_summary_with_idle_days(self):
        conn = db()
        add(conn, MIN_THREAD_ID+1, [item()], day="2026-08-20")
        result = dashboard_data(conn, "2026-01-01", "2026-09-10", 810_000_000, None)
        for key in ("revenue", "cost", "profit", "loan", "real_profit"):
            self.assertEqual(sum(p[key] for p in result["chart"]), result["summary"][key])

    def test_loss_improvement_has_positive_change(self):
        self.assertEqual(_pct(-20, -50), 60)
        self.assertEqual(_pct(0, 0), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
