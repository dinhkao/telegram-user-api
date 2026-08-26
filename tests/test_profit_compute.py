"""Tests profit_dashboard.compute — số liệu cho dashboard lợi nhuận native (#/loi-nhuan)."""
from __future__ import annotations

import json
import sqlite3
import unittest

from product_store import create_products_table, migrate_products_table, upsert_product
from profit_dashboard.compute import (
    customer_detail_data,
    customers_data,
    dashboard_data,
    product_detail_data,
)
from profit_dashboard.queries import MIN_THREAD_ID

_ORDERS_DDL = """
CREATE TABLE orders (
    firebase_key TEXT PRIMARY KEY,
    thread_id    INTEGER UNIQUE,
    channel_id   INTEGER,
    message_id   INTEGER,
    json         TEXT NOT NULL,
    updated_at   INTEGER NOT NULL,
    deleted_at   INTEGER
)
"""


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(_ORDERS_DDL)
    create_products_table(conn)
    migrate_products_table(conn)
    return conn


def _add_order(conn, thread_id, blob):
    conn.execute(
        "INSERT INTO orders (firebase_key, thread_id, json, updated_at) VALUES (?,?,?,0)",
        (f"fk{thread_id}", thread_id, json.dumps(blob)))


class ProfitComputeTest(unittest.TestCase):
    def setUp(self):
        self.conn = _conn()
        upsert_product(self.conn, "SP1", cost_price=5000)
        # kỳ này (20/08): SP1 ×2 @10k → lãi 10k; khách Hoa
        _add_order(self.conn, MIN_THREAD_ID + 1, {
            "created": "2026-08-20T03:00:00+00:00", "customer_name": "Chị Hoa",
            "invoice": [{"sp": "SP1", "sl": 2, "price": 10000}]})
        # kỳ này: SP2 chưa có giá vốn → lãi 0, doanh thu 8k; khách Ba
        _add_order(self.conn, MIN_THREAD_ID + 2, {
            "created": "2026-08-20T04:00:00+00:00", "customer_name": "Anh Ba",
            "invoice": [{"sp": "SP2", "sl": 1, "price": 8000}]})
        # kỳ TRƯỚC (19/08): SP1 ×1 → lãi 5k
        _add_order(self.conn, MIN_THREAD_ID + 3, {
            "created": "2026-08-19T03:00:00+00:00", "customer_name": "Chị Hoa",
            "invoice": [{"sp": "SP1", "sl": 1, "price": 10000}]})

    def test_dashboard_summary_and_prev(self):
        d = dashboard_data(self.conn, "2026-08-20", "2026-08-20", 0, None)
        s = d["summary"]
        self.assertEqual(s["orders"], 2)
        self.assertEqual(s["revenue"], 28000)
        self.assertEqual(s["profit"], 10000)
        self.assertEqual(s["loan"], 0)
        self.assertEqual(s["real_profit"], 10000)
        # kỳ trước = 19/08 (1 ngày): 1 đơn, lãi 5000 → profit +100%
        self.assertEqual(s["prev"], {"revenue": 10000, "cost": 5000,
                                     "profit": 5000, "orders": 1})
        self.assertEqual(s["changes"]["profit"], 100.0)
        # chart có đúng 1 ngày của kỳ
        self.assertEqual([c["day"] for c in d["chart"]], ["2026-08-20"])
        self.assertEqual(d["chart"][0]["profit"], 10000)

    def test_dashboard_products_and_top(self):
        d = dashboard_data(self.conn, "2026-08-20", "2026-08-20", 0, None)
        by_code = {p["code"]: p for p in d["products"]}
        self.assertEqual(by_code["SP1"]["cost_price"], 5000)
        self.assertEqual(by_code["SP1"]["profit"], 10000)
        self.assertEqual(by_code["SP2"]["cost_price"], 0)   # chưa có giá vốn
        self.assertEqual(d["top_customers"][0]["name"], "Chị Hoa")
        self.assertEqual(d["top_products"][0]["code"], "SP1")

    def test_dashboard_loan_prorated(self):
        # vay 12tr/năm, trọng số đều → 1tr/tháng → 1 ngày của tháng 8 ≈ 1tr/31
        d = dashboard_data(self.conn, "2026-08-20", "2026-08-20", 12_000_000, None)
        s = d["summary"]
        self.assertEqual(s["loan"], int(1_000_000 / 31))
        self.assertEqual(s["real_profit"], s["profit"] - s["loan"])

    def test_dashboard_filters_summary_but_not_tops(self):
        # lọc theo SP2 (chỉ đơn của Anh Ba, chưa có vốn): summary/products theo lọc,
        # TOP 5 vẫn tính trên toàn bộ kỳ (như bản gốc)
        d = dashboard_data(self.conn, "2026-08-20", "2026-08-20", 0, None,
                           filter_product="SP2")
        self.assertEqual(d["summary"]["orders"], 1)
        self.assertEqual(d["summary"]["revenue"], 8000)
        self.assertEqual([p["code"] for p in d["products"]], ["SP2"])
        self.assertEqual(d["top_customers"][0]["name"], "Chị Hoa")   # top KHÔNG lọc
        d2 = dashboard_data(self.conn, "2026-08-20", "2026-08-20", 0, None,
                            filter_customer="hoa")
        self.assertEqual(d2["summary"]["orders"], 1)
        self.assertEqual(d2["summary"]["profit"], 10000)

    def test_customers_data(self):
        d = customers_data(self.conn, "2026-08-19", "2026-08-20")
        self.assertEqual(d["customers"][0]["name"], "Chị Hoa")   # lãi cao nhất trước
        hoa = d["customers"][0]
        self.assertEqual(hoa["orders"], 2)
        self.assertEqual(hoa["profit"], 15000)
        self.assertEqual(hoa["product_count"], 1)
        self.assertEqual(d["totals"]["orders"], 3)

    def test_customer_detail(self):
        d = customer_detail_data(self.conn, "chị hoa", "2026-08-19", "2026-08-20")
        self.assertEqual(d["totals"]["orders"], 2)
        self.assertEqual(d["products"][0]["code"], "SP1")
        self.assertEqual(d["products"][0]["qty"], 3)

    def test_product_detail(self):
        d = product_detail_data(self.conn, "sp1", "2026-08-19", "2026-08-20")
        self.assertEqual(d["product"]["cost_price"], 5000)
        self.assertEqual(len(d["orders"]), 2)
        self.assertEqual(d["totals"]["qty"], 3)
        self.assertEqual(d["totals"]["profit"], 15000)


if __name__ == "__main__":
    unittest.main()
