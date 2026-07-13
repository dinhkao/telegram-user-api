"""Regression tests cho product_summary() (aggregate SQL) + list_boxes() (CTE) sau
tối ưu trang Kho: semantics tồn/allocated/transfer/disabled/đổi-mã phải GIỮ NGUYÊN
như bản Python cũ. Nối: inventory_store, product_store, utils.db."""
from __future__ import annotations

import os
import tempfile
import unittest

from inventory_store.allocations import (
    allocate_picks,
    create_allocations_table,
    transfer_between_boxes,
)
from inventory_store.queries import add_boxes, add_place, list_boxes, product_summary, set_disabled
from inventory_store.schema import create_inventory_table, migrate_inventory_table
from product_store import (
    create_products_table,
    get_product,
    migrate_products_table,
    record_code_change,
    upsert_product,
)
from product_store.schema import _invalidate_products_cache
from utils.db import get_connection
from server_app.inventory_routes import _box_summary
from server_app.place_timeline import _current_boxes as current_place_boxes
from server_app.product_timeline import _current_boxes as current_product_boxes


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
        upsert_product(self.conn, "K10", name="Kẹo 10")

    def tearDown(self):
        self.conn.close()
        for ext in ("", "-wal", "-shm"):
            try:
                os.unlink(self.path + ext)
            except FileNotFoundError:
                pass

    def summ(self, code):
        return next((s for s in product_summary(self.conn) if s["product_code"] == code), None)


class ProductSummarySQL(Base):
    def test_plain_and_disabled(self):
        add_boxes(self.conn, "K10", [50, 30, 20])
        bs = list_boxes(self.conn, product_code="K10")
        set_disabled(self.conn, bs[0]["id"], True, "hư")
        s = self.summ("K10")
        self.assertEqual(s["total_count"], 3)
        self.assertEqual(s["disabled_count"], 1)
        self.assertEqual(s["in_stock_count"], 2)
        # thùng disabled KHÔNG tính tồn dù remaining > 0
        self.assertEqual(s["in_stock_total"], sum(b["quantity"] for b in bs) - bs[0]["quantity"])
        self.assertEqual(s["allocated_count"], 0)
        self.assertEqual(s["shipped_count"], 0)

    def test_positive_allocation(self):
        boxes = add_boxes(self.conn, "K10", [50, 30])
        allocate_picks(self.conn, [{"box_id": boxes[0]["id"], "quantity": 50}], 111)
        allocate_picks(self.conn, [{"box_id": boxes[1]["id"], "quantity": 10}], 111)
        s = self.summ("K10")
        # thùng 1 hết (remaining 0) → rớt khỏi in_stock; thùng 2 còn 20
        self.assertEqual(s["in_stock_count"], 1)
        self.assertEqual(s["in_stock_total"], 20)
        self.assertEqual(s["allocated_count"], 2)
        self.assertEqual(s["total_count"], 2)

    def test_transfer_negative_allocation(self):
        boxes = add_boxes(self.conn, "K10", [50, 30])
        r, err = transfer_between_boxes(self.conn, boxes[0]["id"], boxes[1]["id"], 15)
        self.assertIsNone(err)
        s = self.summ("K10")
        # tổng tồn BẢO TOÀN qua transfer (out +15, in −15)
        self.assertEqual(s["in_stock_total"], 80)
        self.assertEqual(s["in_stock_count"], 2)
        # thùng nguồn có allocation dương → allocated_count đếm; thùng nhận SUM âm → không
        self.assertEqual(s["allocated_count"], 1)

    def test_renamed_product_groups_under_current_code(self):
        add_boxes(self.conn, "K10", [50])
        pid = get_product(self.conn, "K10")["id"]
        self.conn.execute("UPDATE products SET code = ? WHERE id = ?", ("K10N", pid))
        record_code_change(self.conn, pid, "K10", "K10N")
        self.conn.commit()
        _invalidate_products_cache()
        add_boxes(self.conn, "K10N", [30])
        self.assertIsNone(self.summ("K10"))
        s = self.summ("K10N")   # thùng cũ (snapshot K10) + mới GỘP 1 nhóm mã hiện hành
        self.assertEqual(s["total_count"], 2)
        self.assertEqual(s["in_stock_total"], 80)
        self.assertEqual(s["product_id"], pid)

    def test_orphan_code_fallback(self):
        # thùng mã lạ (không có trong products) → nhóm theo mã snapshot, product_id NULL
        add_boxes(self.conn, "XLA", [7])
        s = self.summ("XLA")
        self.assertIsNotNone(s)
        self.assertEqual(s["in_stock_total"], 7)
        self.assertIsNone(s["product_id"])

    def test_product_without_boxes_absent(self):
        upsert_product(self.conn, "K20", name="Kẹo 20")
        self.assertIsNone(self.summ("K20"))   # handler /api/inventory tự thêm tồn-0

    def test_sorted_by_code(self):
        upsert_product(self.conn, "A1", name="A")
        add_boxes(self.conn, "K10", [1])
        add_boxes(self.conn, "A1", [1])
        codes = [s["product_code"] for s in product_summary(self.conn)]
        self.assertEqual(codes, sorted(codes))


class ListBoxesCTE(Base):
    def test_remaining_capacity_transfer_semantics(self):
        boxes = add_boxes(self.conn, "K10", [50, 30])
        allocate_picks(self.conn, [{"box_id": boxes[0]["id"], "quantity": 10}], 222)
        transfer_between_boxes(self.conn, boxes[0]["id"], boxes[1]["id"], 5)
        by_id = {b["id"]: b for b in list_boxes(self.conn, product_code="K10")}
        src, dst = by_id[boxes[0]["id"]], by_id[boxes[1]["id"]]
        # nguồn: allocated = 10 (đơn) + 5 (transfer_out) → remaining 35; không nhận gì
        self.assertEqual(src["allocated"], 15)
        self.assertEqual(src["remaining"], 35)
        self.assertEqual(src["transferred_in"], 0)
        self.assertEqual(src["capacity"], 50)
        # đích: allocation ÂM −5 → remaining 35 (tăng); transferred_in 5; capacity 35
        self.assertEqual(dst["allocated"], -5)
        self.assertEqual(dst["remaining"], 35)
        self.assertEqual(dst["transferred_in"], 5)
        self.assertEqual(dst["capacity"], 35)

        # Payload lưới và snapshot timeline phải giữ cùng mốc đầy.
        self.assertEqual(_box_summary(dst)["capacity"], 35)
        place_id = add_place(self.conn, "Kho test")["id"]
        self.conn.execute("UPDATE inventory_boxes SET place_id = ? WHERE id IN (?, ?)",
                          (place_id, boxes[0]["id"], boxes[1]["id"]))
        self.conn.commit()
        by_place = {b["id"]: b for b in current_place_boxes(self.conn, place_id)}
        self.assertEqual(by_place[boxes[1]["id"]]["capacity"], 35)
        pid = get_product(self.conn, "K10")["id"]
        by_product = {b["id"]: b for b in current_product_boxes(self.conn, pid)}
        self.assertEqual(by_product[boxes[1]["id"]]["capacity"], 35)

    def test_no_allocations_defaults_zero(self):
        add_boxes(self.conn, "K10", [9])
        b = list_boxes(self.conn, product_code="K10")[0]
        self.assertEqual(b["allocated"], 0)
        self.assertEqual(b["transferred_in"], 0)
        self.assertEqual(b["remaining"], 9)


if __name__ == "__main__":
    unittest.main()
