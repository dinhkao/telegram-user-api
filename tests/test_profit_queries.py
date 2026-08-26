"""Tests profit_dashboard.queries — feed đơn + lợi nhuận cho dashboard /loi-nhuan.

DB tạm mirror schema orders + products; khoá luật: lọc theo ngày VN, lọc SP/khách,
phân trang, và freeze_all_costs chỉ ghi đơn còn thiếu cost_price.
"""
from __future__ import annotations

import json
import sqlite3
import unittest

from product_store import create_products_table, migrate_products_table, upsert_product
from profit_dashboard.queries import MIN_THREAD_ID, _created_vn, freeze_all_costs, orders_feed

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


class CreatedVNTest(unittest.TestCase):
    def test_iso_utc_to_vn_day(self):
        # 18:30 UTC = 01:30 hôm sau giờ VN
        day, disp = _created_vn("2026-08-20T18:30:00+00:00")
        self.assertEqual(day, "2026-08-21")
        self.assertEqual(disp, "21/08 01:30")

    def test_epoch_ms(self):
        day, _ = _created_vn(1755660000000)  # 2025-08-20 ~09:20 VN
        self.assertEqual(day, "2025-08-20")

    def test_bad_value(self):
        self.assertEqual(_created_vn("not-a-date"), (None, ""))


class OrdersFeedTest(unittest.TestCase):
    def setUp(self):
        self.conn = _conn()
        upsert_product(self.conn, "SP1", cost_price=5000)
        _add_order(self.conn, MIN_THREAD_ID + 1, {
            "created": "2026-08-20T03:00:00+00:00",
            "customer_name": "Chị Hoa",
            "invoice": [{"sp": "SP1", "sl": 2, "price": 10000}],
        })
        _add_order(self.conn, MIN_THREAD_ID + 2, {
            "created": "2026-08-22T03:00:00+00:00",
            "customer_name": "Anh Ba",
            "invoice": [{"sp": "SP2", "sl": 1, "price": 8000}],
        })
        # Đơn cũ hơn mốc thread_id → không bao giờ vào feed
        _add_order(self.conn, MIN_THREAD_ID - 1, {
            "created": "2026-08-22T03:00:00+00:00",
            "invoice": [{"sp": "SP1", "sl": 9, "price": 9000}],
        })

    def test_date_filter_and_profit(self):
        d = orders_feed(self.conn, 1, 50, "2026-08-20", "2026-08-20", None, None)
        self.assertEqual(d["total"], 1)
        row = d["orders"][0]
        self.assertEqual(row["customer"], "Chị Hoa")
        self.assertEqual(row["revenue"], 20000)
        self.assertEqual(row["profit"], 10000)   # (10000-5000)×2

    def test_product_and_customer_filter(self):
        d = orders_feed(self.conn, 1, 50, "2026-08-01", "2026-08-31", "SP2", None)
        self.assertEqual([o["thread_id"] for o in d["orders"]], [MIN_THREAD_ID + 2])
        d = orders_feed(self.conn, 1, 50, "2026-08-01", "2026-08-31", None, "hoa")
        self.assertEqual([o["thread_id"] for o in d["orders"]], [MIN_THREAD_ID + 1])

    def test_paid_only_filter(self):
        _add_order(self.conn, MIN_THREAD_ID + 3, {
            "created": "2026-08-20T05:00:00.000Z", "customer_name": "Chị Hoa",
            "payments": [{"amount": 1}],
            "invoice": [{"sp": "SP1", "sl": 1, "price": 10000}]})
        d = orders_feed(self.conn, 1, 50, "2026-08-01", "2026-08-31", None, None, paid_only=True)
        self.assertEqual([o["thread_id"] for o in d["orders"]], [MIN_THREAD_ID + 3])
        self.assertTrue(d["orders"][0]["has_payment"])
        # không bật: mọi đơn, row nào cũng có cờ has_payment
        d2 = orders_feed(self.conn, 1, 50, "2026-08-01", "2026-08-31", None, None)
        self.assertEqual(d2["total"], 3)
        self.assertFalse(d2["orders"][1]["has_payment"])

    def test_pagination(self):
        d = orders_feed(self.conn, 1, 1, "2026-08-01", "2026-08-31", None, None)
        self.assertEqual(len(d["orders"]), 1)
        self.assertTrue(d["has_more"])
        d2 = orders_feed(self.conn, 2, 1, "2026-08-01", "2026-08-31", None, None)
        self.assertEqual(len(d2["orders"]), 1)
        self.assertFalse(d2["has_more"])


class FreezeCostsTest(unittest.TestCase):
    def test_freezes_only_missing(self):
        conn = _conn()
        upsert_product(conn, "SP1", cost_price=5000)
        _add_order(conn, MIN_THREAD_ID + 1, {
            "invoice": [{"sp": "SP1", "sl": 1, "price": 9000}]})
        _add_order(conn, MIN_THREAD_ID + 2, {
            "invoice": [{"sp": "SP1", "sl": 1, "price": 9000, "cost_price": 4000}]})
        self.assertEqual(freeze_all_costs(conn), 1)
        blob = json.loads(conn.execute(
            "SELECT json FROM orders WHERE thread_id=?",
            (MIN_THREAD_ID + 1,)).fetchone()[0])
        self.assertEqual(blob["invoice"][0]["cost_price"], 5000)
        # Đơn đã có cost_price giữ nguyên số cũ
        blob2 = json.loads(conn.execute(
            "SELECT json FROM orders WHERE thread_id=?",
            (MIN_THREAD_ID + 2,)).fetchone()[0])
        self.assertEqual(blob2["invoice"][0]["cost_price"], 4000)


if __name__ == "__main__":
    unittest.main()
