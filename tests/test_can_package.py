"""Test cờ can_package (đóng gói từ NL) — độc lập với can_produce_directly.
Kiểm: mặc định False, upsert bật/tắt, chuẩn hoá row→dict. Nối: product_store."""
from __future__ import annotations

import os
import tempfile
import unittest

from product_store import create_products_table, migrate_products_table, upsert_product
from product_store.queries import get_product
from product_store.schema import _invalidate_products_cache
from utils.db import get_connection


class CanPackageTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        _invalidate_products_cache()
        create_products_table(self.conn)
        migrate_products_table(self.conn)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def test_default_false(self):
        upsert_product(self.conn, "KEO1", name="Kẹo test")
        p = get_product(self.conn, "KEO1")
        self.assertFalse(p["can_package"])          # mặc định KHÔNG đóng gói
        self.assertTrue(p["can_produce_directly"])  # mặc định SX trực tiếp được

    def test_toggle_independent(self):
        upsert_product(self.conn, "KEO1", name="Kẹo test")
        # bật đóng gói KHÔNG động chạm SX trực tiếp
        upsert_product(self.conn, "KEO1", can_package=True)
        p = get_product(self.conn, "KEO1")
        self.assertTrue(p["can_package"])
        self.assertTrue(p["can_produce_directly"])
        # tắt SX trực tiếp, đóng gói vẫn bật → cả 2 độc lập
        upsert_product(self.conn, "KEO1", can_produce_directly=False)
        p = get_product(self.conn, "KEO1")
        self.assertTrue(p["can_package"])
        self.assertFalse(p["can_produce_directly"])
        # tắt đóng gói → cả 2 tắt (nguyên liệu / hàng mua)
        upsert_product(self.conn, "KEO1", can_package=False)
        p = get_product(self.conn, "KEO1")
        self.assertFalse(p["can_package"])
        self.assertFalse(p["can_produce_directly"])


if __name__ == "__main__":
    unittest.main()
