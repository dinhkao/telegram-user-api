"""Test product_store/units — quy đổi đơn vị hàng hoá (CRUD + validate + convert)."""
from __future__ import annotations

import os
import tempfile
import unittest

from product_store import create_products_table, migrate_products_table, upsert_product
from product_store.queries import get_product
from product_store.schema import _invalidate_products_cache
from product_store import units as pu
from utils.db import get_connection


class ProductUnitsTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        _invalidate_products_cache()
        create_products_table(self.conn)
        migrate_products_table(self.conn)
        upsert_product(self.conn, "KEO1", name="Kẹo test", unit="cây")
        self.pid = get_product(self.conn, "KEO1")["id"]

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def test_add_list_update_delete(self):
        u, err = pu.add_unit(self.conn, self.pid, "thùng", 30, "cây")
        self.assertIsNone(err)
        self.assertEqual(pu.list_units(self.conn, self.pid)[0]["factor"], 30.0)
        u2, err = pu.update_unit(self.conn, self.pid, u["id"], "thùng", 24, "cây")
        self.assertIsNone(err)
        self.assertEqual(pu.list_units(self.conn, self.pid)[0]["factor"], 24.0)
        gone = pu.delete_unit(self.conn, self.pid, u["id"])
        self.assertEqual(gone["name"], "thùng")
        self.assertEqual(pu.list_units(self.conn, self.pid), [])

    def test_validate_chan_trung_va_ti_le_xau(self):
        _, err = pu.add_unit(self.conn, self.pid, "", 30, "cây")
        self.assertIn("Thiếu tên", err)
        _, err = pu.add_unit(self.conn, self.pid, "thùng", 0, "cây")
        self.assertIn("> 0", err)
        _, err = pu.add_unit(self.conn, self.pid, "Cây", 5, "cây")   # đụng đơn vị gốc (bỏ dấu)
        self.assertIn("gốc", err)
        pu.add_unit(self.conn, self.pid, "thùng", 30, "cây")
        _, err = pu.add_unit(self.conn, self.pid, "THÙNG", 24, "cây")  # trùng, khác hoa thường
        self.assertIn("đã có", err)

    def test_convert(self):
        # 1 thùng = 30 cây, 1 kiện = 120 cây → 2 kiện = 8 thùng; 60 cây = 2 thùng
        self.assertEqual(pu.convert(2, 120, 30), 8)
        self.assertEqual(pu.convert(60, 1, 30), 2)
        with self.assertRaises(ValueError):
            pu.convert(1, 30, 0)


if __name__ == "__main__":
    unittest.main()
