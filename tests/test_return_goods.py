"""Test server_app.return_goods.apply_goods_dispositions — xử lý hàng khách trả:
nhập vào thùng có sẵn (+quantity) / tạo thùng mới / xuất hủy box-less; guard đã-xử-lý."""
from __future__ import annotations

import os
import tempfile
import unittest

import disposal_store
import return_store
from inventory_store.allocations import create_allocations_table
from inventory_store.queries import add_boxes, get_box, list_boxes
from inventory_store.schema import create_inventory_table, migrate_inventory_table
from product_store import create_products_table, migrate_products_table, upsert_product
from product_store.schema import _invalidate_products_cache
from server_app.return_goods import apply_goods_dispositions
from utils.db import get_connection


class ReturnGoodsTest(unittest.TestCase):
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
        self.box = add_boxes(self.conn, "KEO1", [100])[0]
        self.ret = return_store.add_return(
            self.conn, "cust-1", [{"sp": "KEO1", "sl": 10, "price": 5000}], 50000, by="duy")

    def tearDown(self):
        self.conn.close()
        _invalidate_products_cache()
        os.unlink(self.path)

    def _qty(self, box_id):
        return float(get_box(self.conn, box_id)["quantity"])

    def _rem(self, box_id):
        q = float(get_box(self.conn, box_id)["quantity"])
        used = self.conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM box_allocations WHERE box_id = ?", (box_id,)).fetchone()[0]
        return q - float(used or 0)

    def test_restock_existing_raises_remaining_not_base_quantity(self):
        extra, err = apply_goods_dispositions(
            self.conn, self.ret["id"],
            [{"sp": "KEO1", "quantity": 4, "action": "restock_existing", "box_id": self.box["id"]}],
            actor="lan")
        self.assertIsNone(err)
        self.assertEqual(self._qty(self.box["id"]), 100)                 # quantity GỐC giữ nguyên
        self.assertEqual(self._rem(self.box["id"]), 104)                 # remaining TĂNG 4
        self.assertEqual(len(extra["result"]["restocked_existing"]), 1)
        # allocation ÂM kind='return_in' (không thổi phồng boxed_total phiếu SX)
        row = self.conn.execute(
            "SELECT kind, quantity FROM box_allocations WHERE box_id = ?", (self.box["id"],)).fetchone()
        self.assertEqual(row["kind"], "return_in")
        self.assertEqual(row["quantity"], -4)
        self.assertIsNotNone(return_store.get_return(self.conn, self.ret["id"])["goods_handled_at"])

    def test_restock_new_creates_box(self):
        before = len(list_boxes(self.conn))
        extra, err = apply_goods_dispositions(
            self.conn, self.ret["id"],
            [{"sp": "KEO1", "quantity": 6, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err)
        self.assertEqual(len(list_boxes(self.conn)), before + 1)
        new_id = extra["result"]["restocked_new"][0]["box_id"]
        self.assertEqual(self._qty(new_id), 6)
        # thùng mới truy nguồn về phiếu trả (guard xoá lẻ + link BoxDetail)
        self.assertEqual(get_box(self.conn, new_id)["source_return_id"], self.ret["id"])

    def test_dispose_creates_box_less_disposal_no_stock_change(self):
        extra, err = apply_goods_dispositions(
            self.conn, self.ret["id"],
            [{"sp": "KEO1", "quantity": 3, "action": "dispose"}], actor="lan")
        self.assertIsNone(err)
        self.assertEqual(self._qty(self.box["id"]), 100)                 # tồn không đổi
        d = extra["disposal"]
        self.assertTrue(d["box_less"])
        self.assertEqual(d["source_return_id"], self.ret["id"])
        self.assertEqual(d["total_quantity"], 3)
        self.assertEqual(extra["result"]["disposal_id"], d["id"])

    def test_mixed_dispositions_one_call(self):
        extra, err = apply_goods_dispositions(
            self.conn, self.ret["id"], [
                {"sp": "KEO1", "quantity": 2, "action": "restock_existing", "box_id": self.box["id"]},
                {"sp": "KEO1", "quantity": 5, "action": "restock_new"},
                {"sp": "KEO1", "quantity": 1, "action": "dispose"},
                {"sp": "KEO1", "quantity": 9, "action": "skip"},
            ], actor="lan")
        self.assertIsNone(err)
        res = extra["result"]
        self.assertEqual((len(res["restocked_existing"]), len(res["restocked_new"]), len(res["disposed"])), (1, 1, 1))
        self.assertEqual(self._qty(self.box["id"]), 100)   # quantity gốc giữ nguyên
        self.assertEqual(self._rem(self.box["id"]), 102)   # remaining +2 (allocation return_in)

    def test_already_handled_guard(self):
        apply_goods_dispositions(self.conn, self.ret["id"], [{"sp": "KEO1", "quantity": 1, "action": "dispose"}])
        extra, err = apply_goods_dispositions(self.conn, self.ret["id"], [{"sp": "KEO1", "quantity": 1, "action": "dispose"}])
        self.assertIsNone(extra)
        self.assertEqual(err, "already")

    def test_not_found_guard(self):
        extra, err = apply_goods_dispositions(self.conn, 99999, [])
        self.assertIsNone(extra)
        self.assertEqual(err, "not_found")

    def test_restock_existing_rejects_wrong_product_box(self):
        # Nhận KEO1 vào thùng KEO2 → dòng bị bỏ qua, tồn KEO2 không đổi.
        upsert_product(self.conn, "KEO2", "Kẹo khác", unit="cây")
        other = add_boxes(self.conn, "KEO2", [50])[0]
        extra, err = apply_goods_dispositions(
            self.conn, self.ret["id"],
            [{"sp": "KEO1", "quantity": 4, "action": "restock_existing", "box_id": other["id"]}],
            actor="lan")
        self.assertIsNone(err)
        self.assertEqual(extra["result"]["restocked_existing"], [])
        self.assertEqual(self._rem(other["id"]), 50)

    def test_restock_existing_rejects_disabled_box(self):
        self.conn.execute("UPDATE inventory_boxes SET disabled = 1 WHERE id = ?", (self.box["id"],))
        extra, err = apply_goods_dispositions(
            self.conn, self.ret["id"],
            [{"sp": "KEO1", "quantity": 4, "action": "restock_existing", "box_id": self.box["id"]}],
            actor="lan")
        self.assertIsNone(err)
        self.assertEqual(extra["result"]["restocked_existing"], [])
        self.assertEqual(self._rem(self.box["id"]), 100)   # không cộng gì

    def test_dispositions_capped_by_slip_quantity(self):
        # Phiếu trả 10 KEO1: dòng vượt trần / SP lạ / cộng dồn quá 10 đều bị bỏ qua.
        upsert_product(self.conn, "KEO2", "Kẹo khác", unit="cây")
        extra, err = apply_goods_dispositions(
            self.conn, self.ret["id"], [
                {"sp": "KEO1", "quantity": 12, "action": "restock_new"},                          # 12 > 10
                {"sp": "KEO2", "quantity": 3, "action": "restock_new"},                           # không có trên phiếu
                {"sp": "KEO1", "quantity": 8, "action": "restock_existing", "box_id": self.box["id"]},  # OK
                {"sp": "KEO1", "quantity": 4, "action": "dispose"},                               # 8+4 > 10
            ], actor="lan")
        self.assertIsNone(err)
        res = extra["result"]
        self.assertEqual(res["restocked_new"], [])
        self.assertEqual(len(res["restocked_existing"]), 1)
        self.assertEqual(res["disposed"], [])
        self.assertIsNone(res["disposal_id"])
        self.assertEqual(self._rem(self.box["id"]), 108)   # chỉ dòng hợp lệ được ghi

    def test_audit_snapshots_for_box_events(self):
        # extra['audit'] = snapshot cho route ghi event kho (box.created / box.return_in)
        extra, err = apply_goods_dispositions(
            self.conn, self.ret["id"],
            [{"sp": "KEO1", "quantity": 4, "action": "restock_existing", "box_id": self.box["id"]},
             {"sp": "KEO1", "quantity": 6, "action": "restock_new"}],
            actor="lan")
        self.assertIsNone(err)
        audit = extra["audit"]
        self.assertEqual(len(audit["created"]), 1)
        self.assertEqual(audit["created"][0]["remaining"], 6)
        self.assertEqual(len(audit["return_in"]), 1)
        rin = audit["return_in"][0]
        self.assertEqual(rin["box_id"], self.box["id"])
        self.assertEqual(rin["taken"], 4)
        self.assertEqual(rin["remaining"], 104)   # tồn SAU khi cộng


if __name__ == "__main__":
    unittest.main()


class ReturnGoodsBulkSplitTest(unittest.TestCase):
    """SP NGUYÊN KIỆN: restock_new tự TÁCH kiện — 75 (kiện 30) → 2 thùng 30 dán nhãn
    + 1 thùng lẻ 15 không nhãn (modal trả hàng không có ô số thùng)."""

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
        from product_store.queries import get_product
        from product_store import units as pu
        pid = get_product(self.conn, "KEO1")["id"]
        u, _ = pu.add_unit(self.conn, pid, "Thùng", 30, "cây")
        upsert_product(self.conn, "KEO1", bulk_unit_id=u["id"])
        self.ret = return_store.add_return(
            self.conn, "cust-1", [{"sp": "KEO1", "sl": 75, "price": 5000}], 375000, by="duy")

    def tearDown(self):
        self.conn.close()
        _invalidate_products_cache()
        os.unlink(self.path)

    def test_tu_tach_kien_va_le(self):
        extra, err = apply_goods_dispositions(
            self.conn, self.ret["id"],
            [{"sp": "KEO1", "quantity": 75, "action": "restock_new"}])
        self.assertIsNone(err)
        boxes = sorted([b for b in list_boxes(self.conn) if b.get("source_return_id") == self.ret["id"]],
                       key=lambda b: -b["quantity"])
        self.assertEqual([b["quantity"] for b in boxes], [30.0, 30.0, 15.0])
        self.assertEqual([b["unit_label"] for b in boxes], ["Thùng", "Thùng", None])
