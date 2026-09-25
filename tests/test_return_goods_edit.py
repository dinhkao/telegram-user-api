"""server_app.return_goods_edit — gỡ từng dòng xử lý hàng trả, phần chưa xử lý,
xử lý tiếp nhiều đợt, sửa hàng trên phiếu đã xử lý (đơn giá luôn đổi được)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

import disposal_store
import return_store
from inventory_store.allocations import create_allocations_table
from inventory_store.queries import add_boxes, get_box
from inventory_store.schema import create_inventory_table, migrate_inventory_table
from product_store import create_products_table, migrate_products_table, upsert_product
from product_store.schema import _invalidate_products_cache
from server_app.return_goods import apply_goods_dispositions
from server_app.return_goods_edit import check_items_cover_handled, goods_pending, revert_goods_line
from utils.db import get_connection


class ReturnGoodsEditTest(unittest.TestCase):
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
        disposal_store.ensure_table(self.conn)
        return_store.ensure_returns_schema(self.conn)
        upsert_product(self.conn, "KEO1", "Kẹo", unit="cây")
        upsert_product(self.conn, "KEO2", "Kẹo khác", unit="cây")
        self.box = add_boxes(self.conn, "KEO1", [100])[0]
        self.rid = return_store.add_return(
            self.conn, "cust-1", [{"sp": "KEO1", "sl": 10, "price": 5000}], 50000, by="duy")["id"]

    def tearDown(self):
        self.conn.close()
        _invalidate_products_cache()
        os.unlink(self.path)

    def _ret(self):
        return return_store.get_return(self.conn, self.rid)

    def _rem(self, box_id):
        q = float(get_box(self.conn, box_id)["quantity"])
        used = self.conn.execute("SELECT COALESCE(SUM(quantity),0) FROM box_allocations WHERE box_id=?",
                                 (box_id,)).fetchone()[0]
        return q - float(used or 0)

    def _handle(self, disps):
        extra, err = apply_goods_dispositions(self.conn, self.rid, disps, actor="lan")
        self.assertIsNone(err)
        return extra

    def test_revert_new_box_then_pending_then_handle_again(self):
        self._handle([{"sp": "KEO1", "quantity": 6, "action": "restock_new"},
                      {"sp": "KEO1", "quantity": 4, "action": "dispose"}])
        self.assertEqual(goods_pending(self.conn, self._ret()), [])
        new_id = self._ret()["goods_result"]["restocked_new"][0]["box_id"]
        extra, err = revert_goods_line(self.conn, self.rid, "restocked_new", 0, actor="duy")
        self.assertIsNone(err)
        self.assertIsNone(get_box(self.conn, new_id))                       # thùng mới bị xoá
        self.assertEqual(extra["audit"]["deleted"][0]["box_id"], new_id)
        self.assertFalse(extra["reset"])                                    # còn dòng hủy
        self.assertEqual(goods_pending(self.conn, self._ret()), [{"sp": "KEO1", "quantity": 6}])
        # xử lý tiếp đúng phần còn lại; vượt thì chặn
        _, err = apply_goods_dispositions(self.conn, self.rid, [{"sp": "KEO1", "quantity": 7, "action": "restock_new"}])
        self.assertIn("vượt", err)
        self._handle([{"sp": "KEO1", "quantity": 6, "action": "restock_existing", "box_id": self.box["id"]}])
        gr = self._ret()["goods_result"]
        self.assertEqual(len(gr["disposed"]), 1)                            # đợt cũ còn nguyên
        self.assertEqual(len(gr["restocked_existing"]), 1)
        self.assertEqual(goods_pending(self.conn, self._ret()), [])

    def test_revert_new_box_blocked_when_allocated(self):
        self._handle([{"sp": "KEO1", "quantity": 10, "action": "restock_new"}])
        new_id = self._ret()["goods_result"]["restocked_new"][0]["box_id"]
        self.conn.execute("INSERT INTO box_allocations (box_id, order_thread_id, quantity, allocated_at, kind)"
                          " VALUES (?, 1, 3, 'x', 'order')", (new_id,))
        extra, err = revert_goods_line(self.conn, self.rid, "restocked_new", 0)
        self.assertIsNone(extra)
        self.assertIn("không gỡ được", err)
        self.assertIsNotNone(get_box(self.conn, new_id))
        self.assertEqual(len(self._ret()["goods_result"]["restocked_new"]), 1)

    def test_revert_existing_checks_remaining(self):
        self._handle([{"sp": "KEO1", "quantity": 10, "action": "restock_existing", "box_id": self.box["id"]}])
        self.assertEqual(self._rem(self.box["id"]), 110)
        # đã xuất 105 → thùng còn 5 < 10 đã cộng → không gỡ được
        self.conn.execute("INSERT INTO box_allocations (box_id, order_thread_id, quantity, allocated_at, kind)"
                          " VALUES (?, 1, 105, 'x', 'order')", (self.box["id"],))
        _, err = revert_goods_line(self.conn, self.rid, "restocked_existing", 0)
        self.assertIn("đã được dùng", err)
        self.conn.execute("DELETE FROM box_allocations WHERE kind='order'")
        extra, err = revert_goods_line(self.conn, self.rid, "restocked_existing", 0)
        self.assertIsNone(err)
        self.assertEqual(self._rem(self.box["id"]), 100)
        self.assertEqual(extra["audit"]["return_in_removed"][0]["taken"], 10)
        self.assertTrue(extra["reset"])                                     # gỡ hết → về chưa xử lý
        r = self._ret()
        self.assertIsNone(r["goods_handled_at"])
        self.assertIsNone(r["goods_result"])

    def test_revert_disposed_shrinks_then_soft_deletes_disposal(self):
        self._handle([{"sp": "KEO1", "quantity": 3, "action": "dispose"},
                      {"sp": "KEO1", "quantity": 7, "action": "dispose"}])
        did = self._ret()["goods_result"]["disposal_id"]
        _, err = revert_goods_line(self.conn, self.rid, "disposed", 0)
        self.assertIsNone(err)
        items, deleted = self.conn.execute("SELECT items, deleted_at FROM disposal_slips WHERE id=?", (did,)).fetchone()
        self.assertEqual([i["quantity"] for i in json.loads(items)], [7.0])
        self.assertIsNone(deleted)
        _, err = revert_goods_line(self.conn, self.rid, "disposed", 0)
        self.assertIsNone(err)
        self.assertIsNotNone(self.conn.execute("SELECT deleted_at FROM disposal_slips WHERE id=?", (did,)).fetchone()[0])
        self.assertIsNone(self._ret()["goods_handled_at"])

    def test_bad_index_and_kind(self):
        self._handle([{"sp": "KEO1", "quantity": 10, "action": "dispose"}])
        self.assertIn("không còn", revert_goods_line(self.conn, self.rid, "disposed", 5)[1])
        self.assertIn("không hợp lệ", revert_goods_line(self.conn, self.rid, "xx", 0)[1])
        self.assertEqual(revert_goods_line(self.conn, 9999, "disposed", 0)[1], "not_found")

    def test_items_cover_handled(self):
        self._handle([{"sp": "KEO1", "quantity": 6, "action": "restock_new"}])   # 4 còn chưa xử lý
        r = self._ret()
        ok = [{"sp": "KEO1", "sl": 10, "price": 9000}]
        self.assertIsNone(check_items_cover_handled(self.conn, r, ok))           # đổi đơn giá
        self.assertIsNone(check_items_cover_handled(self.conn, r, [{"sp": "KEO1", "sl": 6, "price": 5000}]))
        self.assertIn("không được nhỏ hơn",
                      check_items_cover_handled(self.conn, r, [{"sp": "KEO1", "sl": 5, "price": 5000}]))
        self.assertIn("KEO1", check_items_cover_handled(self.conn, r, [{"sp": "KEO2", "sl": 10, "price": 5000}]))
        # thêm mã mới / tăng SL → phần chưa xử lý tăng theo
        r2 = {**r, "items": [{"sp": "KEO1", "sl": 8, "price": 5000}, {"sp": "KEO2", "sl": 3, "price": 1}]}
        self.assertEqual(goods_pending(self.conn, r2), [{"sp": "KEO1", "quantity": 2}, {"sp": "KEO2", "quantity": 3}])


if __name__ == "__main__":
    unittest.main()
