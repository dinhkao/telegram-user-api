"""Test logic cảnh báo THIẾU HÀNG (server_app.stock_alert._compute): tính tập THIẾU
theo mã từ invoice so với tồn (inventory_store.product_summary), dedup theo dấu
$.stock_alert_state để không báo lặp. Chỉ test hàm thuần _compute (không async/FCM)."""
from __future__ import annotations

import os
import tempfile
import unittest

from inventory_store.allocations import create_allocations_table
from inventory_store.queries import add_boxes
from inventory_store.schema import create_inventory_table, migrate_inventory_table
from order_store import _create_order, _update_order_json_field
from product_store import create_products_table, migrate_products_table, upsert_product
from product_store.schema import _invalidate_products_cache
from server_app.stock_alert import _compute
from utils.db import get_connection

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

THREAD = 7001


class StockAlert(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        _invalidate_products_cache()
        self.conn.execute(_ORDERS_DDL)
        create_products_table(self.conn)
        migrate_products_table(self.conn)
        create_inventory_table(self.conn)
        migrate_inventory_table(self.conn)
        create_allocations_table(self.conn)
        upsert_product(self.conn, "K10", name="Kẹo 10")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        for ext in ("", "-wal", "-shm"):
            try:
                os.unlink(self.path + ext)
            except FileNotFoundError:
                pass

    def _order(self, invoice):
        _create_order(self.conn, f"fk-{THREAD}", THREAD, 111, 222,
                      {"text": "Đơn test", "invoice": invoice})
        self.conn.commit()

    def test_short_when_stock_below_need(self):
        add_boxes(self.conn, "K10", [30])            # tồn 30
        self.conn.commit()
        self._order([{"sp": "K10", "sl": 50}])       # cần 50 > 30
        res = _compute(self.conn, THREAD)
        self.assertIsNotNone(res)
        self.assertIn("K10", res["short"])
        need, have = res["short"]["K10"]
        self.assertEqual(need, 50.0)
        self.assertEqual(have, 30.0)

    def test_no_alert_when_enough(self):
        add_boxes(self.conn, "K10", [50, 30])        # tồn 80 ≥ 50
        self.conn.commit()
        self._order([{"sp": "K10", "sl": 50}])
        self.assertIsNone(_compute(self.conn, THREAD))

    def test_dedup_same_shortage(self):
        add_boxes(self.conn, "K10", [10])
        self.conn.commit()
        self._order([{"sp": "K10", "sl": 40}])
        self.assertIsNotNone(_compute(self.conn, THREAD))   # lần đầu: báo
        self.assertIsNone(_compute(self.conn, THREAD))      # tập thiếu KHÔNG đổi → None

    def test_realert_when_need_changes(self):
        add_boxes(self.conn, "K10", [10])
        self.conn.commit()
        self._order([{"sp": "K10", "sl": 40}])
        self.assertIsNotNone(_compute(self.conn, THREAD))
        _update_order_json_field(self.conn, THREAD, "$.invoice", [{"sp": "K10", "sl": 60}])
        res = _compute(self.conn, THREAD)                   # số cần đổi → báo lại
        self.assertIsNotNone(res)
        self.assertEqual(res["short"]["K10"][0], 60.0)

    def test_cleared_when_restocked(self):
        add_boxes(self.conn, "K10", [10])
        self.conn.commit()
        self._order([{"sp": "K10", "sl": 40}])
        self.assertIsNotNone(_compute(self.conn, THREAD))
        add_boxes(self.conn, "K10", [50])                   # tồn 60 ≥ 40 → hết thiếu
        self.conn.commit()
        self.assertIsNone(_compute(self.conn, THREAD))      # xoá dấu, không báo
        self.assertIsNone(_compute(self.conn, THREAD))

    def test_empty_invoice_no_alert(self):
        add_boxes(self.conn, "K10", [10])
        self.conn.commit()
        self._order([])
        self.assertIsNone(_compute(self.conn, THREAD))


if __name__ == "__main__":
    unittest.main()
