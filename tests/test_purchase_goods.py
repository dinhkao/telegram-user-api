"""Test server_app.purchase_goods.apply_purchase_receipt — nhập kho hàng mua về:
nhập vào thùng có sẵn (allocation ÂM 'purchase_in') / tạo thùng mới (source_purchase_id);
guard đã-nhập; khoá không có trong hàng trả: KHÔNG có action dispose."""
from __future__ import annotations

import os
import tempfile
import unittest

import purchase_store
from inventory_store.allocations import create_allocations_table
from inventory_store.queries import add_boxes, get_box, list_boxes
from inventory_store.schema import create_inventory_table, migrate_inventory_table
from product_store import create_products_table, migrate_products_table, upsert_product
from product_store.schema import _invalidate_products_cache
from server_app.purchase_goods import apply_purchase_receipt
from utils.db import get_connection


class PurchaseGoodsTest(unittest.TestCase):
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
        purchase_store.ensure_purchases_schema(self.conn)
        upsert_product(self.conn, "KEO1", "Kẹo", unit="cây")
        self.box = add_boxes(self.conn, "KEO1", [100])[0]
        self.pu = purchase_store.add_purchase(
            self.conn, 1, [{"sp": "KEO1", "sl": 20, "price": 5000}], 100000, by="duy")

    def tearDown(self):
        self.conn.close()
        _invalidate_products_cache()
        os.unlink(self.path)

    def _rem(self, box_id):
        q = float(get_box(self.conn, box_id)["quantity"])
        used = self.conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM box_allocations WHERE box_id = ?", (box_id,)).fetchone()[0]
        return q - float(used or 0)

    def test_restock_existing_negative_purchase_in_allocation(self):
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 20, "action": "restock_existing", "box_id": self.box["id"]}],
            actor="lan")
        self.assertIsNone(err)
        self.assertEqual(float(get_box(self.conn, self.box["id"])["quantity"]), 100)  # quantity GỐC giữ nguyên
        self.assertEqual(self._rem(self.box["id"]), 120)                              # remaining TĂNG 20
        row = self.conn.execute(
            "SELECT kind, quantity, order_thread_id FROM box_allocations WHERE box_id = ?",
            (self.box["id"],)).fetchone()
        self.assertEqual(row["kind"], "purchase_in")
        self.assertEqual(row["quantity"], -20)
        self.assertEqual(row["order_thread_id"], self.pu["id"])
        got = purchase_store.get_purchase(self.conn, self.pu["id"])
        self.assertIsNotNone(got["goods_handled_at"])
        self.assertEqual(len(got["goods_result"]["restocked_existing"]), 1)

    def test_restock_new_creates_box_with_source_purchase_id(self):
        before = len(list_boxes(self.conn))
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 15, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err)
        self.assertEqual(len(list_boxes(self.conn)), before + 1)
        new_id = extra["result"]["restocked_new"][0]["box_id"]
        b = get_box(self.conn, new_id)
        self.assertEqual(float(b["quantity"]), 15)
        self.assertEqual(b["source_purchase_id"], self.pu["id"])
        self.assertIn(f"#{self.pu['id']}", b["note"])

    def test_restock_new_count_creates_multiple_boxes(self):
        # count = số thùng giống nhau (như nhập thùng phiếu SX); mỗi thùng `quantity` hàng.
        before = len(list_boxes(self.conn))
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 30, "count": 3, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err)
        self.assertEqual(len(list_boxes(self.conn)), before + 3)   # 3 thùng mới
        news = extra["result"]["restocked_new"]
        self.assertEqual(len(news), 3)                             # 1 entry / thùng
        for e in news:
            self.assertEqual(float(get_box(self.conn, e["box_id"])["quantity"]), 30)
        self.assertEqual(len(set(e["box_id"] for e in news)), 3)   # 3 thùng riêng biệt

    def test_second_apply_blocked(self):
        _, err = apply_purchase_receipt(self.conn, self.pu["id"], [], actor="lan")
        self.assertIsNone(err)
        _, err2 = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 5, "action": "restock_new"}], actor="hai")
        self.assertEqual(err2, "already")
        self.assertEqual(len(list_boxes(self.conn)), 1)   # không tạo thêm thùng

    def test_invalid_lines_skipped_silently(self):
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "", "quantity": 5, "action": "restock_new"},                       # thiếu mã
             {"sp": "KEO1", "quantity": 0, "action": "restock_new"},                   # số ≤ 0
             {"sp": "KEO1", "quantity": 3, "action": "restock_existing", "box_id": 999},  # thùng không có
             {"sp": "KEO1", "quantity": 7, "action": "skip"},
             {"sp": "KEO1", "quantity": 2, "action": "dispose"},                       # KHÔNG hỗ trợ với hàng mua
             {"sp": "KEO1", "quantity": 4, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err)
        self.assertEqual(len(extra["result"]["restocked_new"]), 1)
        self.assertEqual(extra["result"]["restocked_new"][0]["quantity"], 4)
        self.assertEqual(extra["result"]["restocked_existing"], [])

    def test_mark_deleted_boxes_flags_removed_box(self):
        from inventory_store.queries import delete_box
        from server_app.purchase_goods import mark_deleted_boxes
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 15, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err)
        new_id = extra["result"]["restocked_new"][0]["box_id"]
        row = mark_deleted_boxes(self.conn, purchase_store.get_purchase(self.conn, self.pu["id"]))
        self.assertNotIn("box_deleted", row["goods_result"]["restocked_new"][0])  # thùng còn → không cờ
        delete_box(self.conn, new_id)   # admin xoá hẳn thùng
        row2 = mark_deleted_boxes(self.conn, purchase_store.get_purchase(self.conn, self.pu["id"]))
        self.assertTrue(row2["goods_result"]["restocked_new"][0]["box_deleted"])

    # ── HỦY CHỐT nhập kho (undo_purchase_receipt) ──
    def _receive_both(self):
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 20, "action": "restock_existing", "box_id": self.box["id"]},
             {"sp": "KEO1", "quantity": 15, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err)
        return extra["result"]["restocked_new"][0]["box_id"]

    def test_undo_receipt_full_revert(self):
        from server_app.purchase_goods import undo_purchase_receipt
        new_id = self._receive_both()
        info, err = undo_purchase_receipt(self.conn, self.pu["id"])
        self.assertIsNone(err)
        self.assertIn(new_id, info["deleted_boxes"])
        self.assertIsNone(get_box(self.conn, new_id))            # thùng mới bị xoá
        self.assertEqual(self._rem(self.box["id"]), 100)         # thùng có sẵn về như cũ
        got = purchase_store.get_purchase(self.conn, self.pu["id"])
        self.assertIsNone(got["goods_handled_at"])               # phiếu mở khoá lại
        self.assertIsNone(got["goods_result"])
        # nhập kho LẠI được sau khi hủy chốt
        _, err2 = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 5, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err2)

    def test_undo_blocked_when_new_box_used(self):
        from inventory_store.allocations import allocate_picks
        from server_app.purchase_goods import undo_purchase_receipt
        new_id = self._receive_both()
        allocate_picks(self.conn, [{"box_id": new_id, "quantity": 3}], 555)   # đã xuất cho đơn
        info, err = undo_purchase_receipt(self.conn, self.pu["id"])
        self.assertIsNotNone(err)
        self.assertIn("đã được dùng", err)
        self.assertIsNotNone(get_box(self.conn, new_id))                       # KHÔNG xoá gì (all-or-nothing)
        self.assertEqual(self._rem(self.box["id"]), 120)
        self.assertIsNotNone(purchase_store.get_purchase(self.conn, self.pu["id"])["goods_handled_at"])

    def test_undo_blocked_when_received_stock_consumed(self):
        from inventory_store.allocations import allocate_picks
        from server_app.purchase_goods import undo_purchase_receipt
        apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 20, "action": "restock_existing", "box_id": self.box["id"]}],
            actor="lan")
        # tiêu 110/120 → remaining 10 < 20 đã cộng ⇒ phần hàng nhập đã bị dùng
        allocate_picks(self.conn, [{"box_id": self.box["id"], "quantity": 110}], 556)
        info, err = undo_purchase_receipt(self.conn, self.pu["id"])
        self.assertIsNotNone(err)
        self.assertIn("đã dùng một phần", err)

    def test_undo_requires_handled(self):
        from server_app.purchase_goods import undo_purchase_receipt
        _, err = undo_purchase_receipt(self.conn, self.pu["id"])
        self.assertIn("chưa chốt", err)

    def test_not_found_and_deleted(self):
        _, err = apply_purchase_receipt(self.conn, 999, [], actor="lan")
        self.assertEqual(err, "not_found")
        purchase_store.soft_delete_purchase(self.conn, self.pu["id"], by="admin")
        _, err2 = apply_purchase_receipt(self.conn, self.pu["id"], [], actor="lan")
        self.assertEqual(err2, "not_found")


if __name__ == "__main__":
    unittest.main()
