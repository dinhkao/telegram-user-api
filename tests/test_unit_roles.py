"""VAI ĐƠN VỊ (products.bulk/display/stocktake_unit_id — docs/plan-don-vi-hang-hoa.md):
resolve unit_role (NULL/0/id), self_container derive từ vai 📦, validate giá trị vai,
chặn xoá đơn vị đang giữ vai, upsert set/clear vai qua sentinel _UNSET."""
from __future__ import annotations

import os
import tempfile
import unittest

from product_store import create_products_table, migrate_products_table, upsert_product
from product_store.queries import get_product
from product_store.schema import _invalidate_products_cache
from product_store import units as pu
from utils.db import get_connection


class UnitRolesTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        _invalidate_products_cache()
        create_products_table(self.conn)
        migrate_products_table(self.conn)
        upsert_product(self.conn, "KEO1", name="Kẹo test", unit="cây")
        self.pid = get_product(self.conn, "KEO1")["id"]
        self.thung, _ = pu.add_unit(self.conn, self.pid, "Thùng", 30, "cây")

    def tearDown(self):
        self.conn.close()
        _invalidate_products_cache()
        os.unlink(self.path)

    def _p(self):
        return get_product(self.conn, "KEO1")

    def test_self_container_derive_tu_vai_bulk(self):
        self.assertFalse(self._p()["self_container"])                       # chưa chỉ định
        upsert_product(self.conn, "KEO1", bulk_unit_id=0)                    # vai = đơn vị gốc
        self.assertTrue(self._p()["self_container"])
        upsert_product(self.conn, "KEO1", bulk_unit_id=self.thung["id"])     # vai = đơn vị phụ
        self.assertTrue(self._p()["self_container"])
        upsert_product(self.conn, "KEO1", bulk_unit_id=None)                 # xoá chỉ định
        self.assertFalse(self._p()["self_container"])
        # đơn vị đếm thùng/kiện KHÔNG còn tự thành nguyên kiện (hết suy từ tên)
        upsert_product(self.conn, "KEO1", unit="thùng")
        self.assertFalse(self._p()["self_container"])

    def test_unit_role_resolve(self):
        units = pu.list_units(self.conn, self.pid)
        self.assertIsNone(pu.unit_role(self._p(), units, "bulk"))
        upsert_product(self.conn, "KEO1", bulk_unit_id=0, display_unit_id=self.thung["id"])
        p = self._p()
        self.assertEqual(pu.unit_role(p, units, "bulk"), {"id": 0, "name": "cây", "factor": 1.0})
        self.assertEqual(pu.unit_role(p, units, "display"),
                         {"id": self.thung["id"], "name": "Thùng", "factor": 30.0})
        self.assertIsNone(pu.unit_role(p, units, "stocktake"))
        roles = pu.resolve_roles(self.conn, p)
        self.assertEqual(roles["display_unit"]["name"], "Thùng")
        self.assertIsNone(roles["stocktake_unit"])

    def test_validate_role_value(self):
        self.assertIsNone(pu.validate_role_value(self.conn, self.pid, None))
        self.assertIsNone(pu.validate_role_value(self.conn, self.pid, 0))
        self.assertIsNone(pu.validate_role_value(self.conn, self.pid, self.thung["id"]))
        self.assertIn("không thuộc", pu.validate_role_value(self.conn, self.pid, 99999))
        self.assertIn("không hợp lệ", pu.validate_role_value(self.conn, self.pid, "xyz"))

    def test_chan_xoa_don_vi_dang_giu_vai(self):
        upsert_product(self.conn, "KEO1", stocktake_unit_id=self.thung["id"])
        gone, err = pu.delete_unit(self.conn, self.pid, self.thung["id"])
        self.assertIsNone(gone)
        self.assertIn("kiểm kho", err)
        upsert_product(self.conn, "KEO1", stocktake_unit_id=None)            # gỡ vai → xoá được
        gone, err = pu.delete_unit(self.conn, self.pid, self.thung["id"])
        self.assertIsNone(err)
        self.assertEqual(gone["name"], "Thùng")


if __name__ == "__main__":
    unittest.main()
