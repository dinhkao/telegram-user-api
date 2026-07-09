"""Tests Phase 1 product-id cho kho + công thức: thùng/recipe trỏ product_id,
hiển thị mã HIỆN HÀNH sau đổi mã (join theo id), lọc/tiêu hao/chuyển thùng nhận
cả mã cũ, mixed thùng trước-và-sau đổi mã vẫn là CÙNG SP."""
from __future__ import annotations

import os
import tempfile
import unittest

from inventory_store.allocations import (
    create_allocations_table,
    fifo_consume,
    transfer_between_boxes,
)
from inventory_store.queries import add_boxes, get_box, list_boxes, product_summary
from inventory_store.schema import create_inventory_table, migrate_inventory_table
from product_store import (
    create_products_table,
    get_product,
    migrate_products_table,
    record_code_change,
    upsert_product,
)
from product_store.schema import _invalidate_products_cache
from recipe_store.queries import list_recipe, recipe_needs, set_recipe_line
from recipe_store.schema import create_recipe_table
from utils.db import get_connection


class Base(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        _invalidate_products_cache()
        create_products_table(self.conn)
        migrate_products_table(self.conn)
        create_inventory_table(self.conn)
        migrate_inventory_table(self.conn)
        create_allocations_table(self.conn)
        create_recipe_table(self.conn)
        upsert_product(self.conn, "K10", name="Kẹo 10")
        self.pid = get_product(self.conn, "K10")["id"]

    def tearDown(self):
        self.conn.close()
        for ext in ("", "-wal", "-shm"):
            try:
                os.unlink(self.path + ext)
            except FileNotFoundError:
                pass

    def _rename(self, old, new, pid):
        self.conn.execute("UPDATE products SET code = ? WHERE id = ?", (new, pid))
        record_code_change(self.conn, pid, old, new)
        self.conn.commit()
        _invalidate_products_cache()


class BoxesById(Base):
    def test_add_boxes_stores_pid(self):
        boxes = add_boxes(self.conn, "K10", [50, 70])
        self.assertTrue(all(b["product_id"] == self.pid for b in boxes))

    def test_display_live_code_after_rename(self):
        add_boxes(self.conn, "K10", [50])
        self._rename("K10", "K10X", self.pid)
        boxes = list_boxes(self.conn)
        self.assertEqual(boxes[0]["product_code"], "K10X")  # mã hiện hành, không phải snapshot
        self.assertEqual(get_box(self.conn, boxes[0]["id"])["product_code"], "K10X")
        # lọc bằng mã CŨ vẫn ra thùng (resolve qua history)
        self.assertEqual(len(list_boxes(self.conn, product_code="K10")), 1)
        self.assertEqual(len(list_boxes(self.conn, product_code="K10X")), 1)
        # tổng tồn gom về mã mới
        summ = product_summary(self.conn)
        self.assertEqual(summ[0]["product_code"], "K10X")
        self.assertEqual(summ[0]["product_id"], self.pid)

    def test_transfer_mixed_old_new_snapshot_same_product(self):
        b1 = add_boxes(self.conn, "K10", [50])[0]          # snapshot K10
        self._rename("K10", "K10X", self.pid)
        b2 = add_boxes(self.conn, "K10X", [30])[0]         # snapshot K10X, cùng SP
        res, err = transfer_between_boxes(self.conn, b1["id"], b2["id"], 10)
        self.assertIsNone(err)                              # cùng product_id → cho chuyển
        self.assertEqual(res["quantity"], 10)

    def test_fifo_consume_accepts_old_code(self):
        add_boxes(self.conn, "K10", [50])
        self._rename("K10", "K10X", self.pid)
        summary = fifo_consume(self.conn, 999, [{"code": "K10", "amount": 20}])
        self.assertEqual(summary[0]["consumed"], 20)        # mã cũ vẫn tiêu đúng kho

    def test_add_boxes_with_old_code_normalizes(self):
        self._rename("K10", "K10X", self.pid)
        boxes = add_boxes(self.conn, "K10", [40])           # gõ mã cũ
        self.assertEqual(boxes[0]["product_code"], "K10X")  # lưu mã hiện hành
        self.assertEqual(boxes[0]["product_id"], self.pid)


class RecipesById(Base):
    def setUp(self):
        super().setUp()
        upsert_product(self.conn, "NL1", name="Nguyên liệu 1")
        self.nl_id = get_product(self.conn, "NL1")["id"]

    def test_recipe_lives_through_rename(self):
        set_recipe_line(self.conn, "K10", "NL1", 2.5)
        self._rename("NL1", "NLX", self.nl_id)
        lines = list_recipe(self.conn, "K10")
        self.assertEqual(lines[0]["ingredient_code"], "NLX")  # mã NL hiện hành
        needs = recipe_needs(self.conn, "K10", 10)
        self.assertEqual(needs[0], {"code": "NLX", "amount": 25.0})
        # đổi mã cả thành phẩm — tra bằng mã cũ lẫn mới đều ra
        self._rename("K10", "K10X", self.pid)
        self.assertEqual(len(list_recipe(self.conn, "K10")), 1)
        self.assertEqual(len(list_recipe(self.conn, "K10X")), 1)

    def test_set_recipe_old_code_normalizes_and_upserts(self):
        set_recipe_line(self.conn, "K10", "NL1", 2.0)
        self._rename("NL1", "NLX", self.nl_id)
        # sửa ratio bằng MÃ CŨ → phải update dòng cũ (không tạo dòng đôi)
        set_recipe_line(self.conn, "K10", "NL1", 3.0)
        lines = list_recipe(self.conn, "K10")
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["ratio"], 3.0)


if __name__ == "__main__":
    unittest.main()
