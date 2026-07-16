"""KHO ĐẶC BIỆT nguồn NL phụ (inventory_places.aux_source): tối đa 1 kho —
bật kho mới tự tắt kho cũ; backfill theo tên khi thêm cột."""
from __future__ import annotations

import os
import tempfile
import unittest

from inventory_store import add_place, aux_source_place, set_place_aux_source
from inventory_store.schema import create_inventory_table, migrate_inventory_table
from product_store import create_products_table, migrate_products_table
from product_store.schema import _invalidate_products_cache
from utils.db import get_connection


class AuxSourcePlaceTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        _invalidate_products_cache()
        create_products_table(self.conn)
        migrate_products_table(self.conn)
        create_inventory_table(self.conn)
        migrate_inventory_table(self.conn)
        self.a = add_place(self.conn, "Kho A")
        self.b = add_place(self.conn, "Kho nguyên liệu đang dùng")

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def test_single_special_place(self):
        self.assertIsNone(aux_source_place(self.conn))
        p = set_place_aux_source(self.conn, self.a["id"], True)
        self.assertEqual(p["aux_source"], 1)
        self.assertEqual(aux_source_place(self.conn)["id"], self.a["id"])
        # bật kho B → kho A tự tắt (chỉ 1 kho đặc biệt)
        set_place_aux_source(self.conn, self.b["id"], True)
        self.assertEqual(aux_source_place(self.conn)["id"], self.b["id"])
        row = self.conn.execute(
            "SELECT aux_source FROM inventory_places WHERE id = ?", (self.a["id"],)).fetchone()
        self.assertEqual(row[0], 0)
        # tắt → không còn ràng buộc
        set_place_aux_source(self.conn, self.b["id"], False)
        self.assertIsNone(aux_source_place(self.conn))


if __name__ == "__main__":
    unittest.main()
