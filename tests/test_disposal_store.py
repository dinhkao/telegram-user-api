"""Test disposal_store: tạo phiếu hủy trừ tồn nguyên tử, kẹp remaining, bắt buộc
lý do, xoá phiếu hoàn tồn (allocations kind='disposal' bị gỡ)."""
from __future__ import annotations

import os
import tempfile
import unittest

import disposal_store
from inventory_store.allocations import allocate_picks, create_allocations_table
from inventory_store.queries import add_boxes, get_box
from inventory_store.schema import create_inventory_table, migrate_inventory_table
from product_store import create_products_table, migrate_products_table, upsert_product
from product_store.schema import _invalidate_products_cache
from utils.db import get_connection
from audit_log import init_audit_db


class DisposalStoreTest(unittest.TestCase):
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
        upsert_product(self.conn, "KEO1", "Kẹo test")
        self.box = add_boxes(self.conn, "KEO1", [100])[0]

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def _remaining(self, box_id):
        box = get_box(self.conn, box_id)
        return float(box["remaining"]) if box and "remaining" in box.keys() else None

    def test_create_requires_reason_and_picks(self):
        slip, err = disposal_store.create_disposal(self.conn, [{"box_id": self.box["id"]}], reason="", by="duy")
        self.assertIsNone(slip)
        self.assertIn("lý do", err)
        slip, err = disposal_store.create_disposal(self.conn, [], reason="hư hỏng", by="duy")
        self.assertIsNone(slip)

    def test_create_reduces_stock_and_snapshots_items(self):
        slip, err = disposal_store.create_disposal(
            self.conn, [{"box_id": self.box["id"], "quantity": 30}], reason="Kẹo chảy nước", by="duy")
        self.assertIsNone(err)
        self.assertEqual(slip["reason"], "Kẹo chảy nước")
        self.assertEqual(slip["total_quantity"], 30)
        self.assertEqual(slip["items"][0]["box_id"], self.box["id"])
        self.assertEqual(slip["items"][0]["product_code"], "KEO1")
        # remaining thùng giảm qua allocation kind='disposal'
        row = self.conn.execute(
            "SELECT kind, quantity, order_thread_id FROM box_allocations WHERE box_id = ?",
            (self.box["id"],)).fetchone()
        self.assertEqual(row["kind"], "disposal")
        self.assertEqual(row["quantity"], 30)
        self.assertEqual(row["order_thread_id"], slip["id"])

    def test_quantity_clamped_to_remaining_and_full_box_default(self):
        allocate_picks(self.conn, [{"box_id": self.box["id"], "quantity": 90}], 999, kind="order")
        slip, err = disposal_store.create_disposal(
            self.conn, [{"box_id": self.box["id"], "quantity": 50}], reason="vỡ", by="duy")
        self.assertIsNone(err)
        self.assertEqual(slip["total_quantity"], 10)  # kẹp theo remaining

    def test_create_rolls_back_when_no_stock(self):
        allocate_picks(self.conn, [{"box_id": self.box["id"]}], 999, kind="order")  # lấy hết
        slip, err = disposal_store.create_disposal(
            self.conn, [{"box_id": self.box["id"]}], reason="hết hạn", by="duy")
        self.assertIsNone(slip)
        self.assertIn("hết hàng", err)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM disposal_slips").fetchone()[0], 0)

    def test_delete_restores_stock_and_soft_deletes(self):
        slip, _ = disposal_store.create_disposal(
            self.conn, [{"box_id": self.box["id"], "quantity": 40}], reason="mốc", by="duy")
        restored, err = disposal_store.delete_disposal(self.conn, slip["id"], by="duy")
        self.assertIsNone(err)
        self.assertEqual(restored, 1)
        left = self.conn.execute(
            "SELECT COUNT(*) FROM box_allocations WHERE box_id = ?", (self.box["id"],)).fetchone()[0]
        self.assertEqual(left, 0)  # tồn hoàn lại
        self.assertNotIn(slip["id"], [s["id"] for s in disposal_store.list_disposals(self.conn)])
        self.assertIsNotNone(disposal_store.get_disposal(self.conn, slip["id"])["deleted_at"])
        # xoá lần 2 → lỗi
        restored, err = disposal_store.delete_disposal(self.conn, slip["id"], by="duy")
        self.assertEqual(restored, 0)
        self.assertIn("đã xoá", err)

    def test_manual_disposal_box_less_records_without_touching_stock(self):
        before = self._remaining(self.box["id"])
        slip, err = disposal_store.create_manual_disposal(
            self.conn, [{"product_code": "keo1", "quantity": 7, "product_unit": "cây"},
                        {"sp": "KEO1", "sl": 3}],
            reason="Hàng khách trả bị mốc", by="duy", source_return_id=42)
        self.assertIsNone(err)
        self.assertTrue(slip["box_less"])
        self.assertEqual(slip["source_return_id"], 42)
        self.assertEqual(slip["total_quantity"], 10)               # 7 + 3
        self.assertEqual(slip["items"][0]["product_code"], "KEO1")  # chuẩn hoá hoa
        self.assertIsNone(slip["items"][0].get("box_id"))
        # KHÔNG tạo allocation, KHÔNG trừ tồn thùng
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM box_allocations").fetchone()[0], 0)
        self.assertEqual(self._remaining(self.box["id"]), before)

    def test_manual_disposal_requires_reason_and_items(self):
        slip, err = disposal_store.create_manual_disposal(self.conn, [{"sp": "KEO1", "sl": 5}], reason="  ")
        self.assertIsNone(slip)
        self.assertIn("lý do", err)
        slip, err = disposal_store.create_manual_disposal(self.conn, [{"sp": "", "sl": 0}], reason="hủy")
        self.assertIsNone(slip)
        self.assertIn("Không có hàng", err)

    def test_delete_box_less_soft_deletes_no_restore(self):
        slip, _ = disposal_store.create_manual_disposal(
            self.conn, [{"product_code": "KEO1", "quantity": 4}], reason="trả hủy", by="duy")
        restored, err = disposal_store.delete_disposal(self.conn, slip["id"], by="duy")
        self.assertIsNone(err)
        self.assertEqual(restored, 0)   # không có allocation để hoàn
        self.assertIsNotNone(disposal_store.get_disposal(self.conn, slip["id"])["deleted_at"])

    def test_timeline_backfill_is_idempotent(self):
        init_audit_db(self.path)
        slip, _ = disposal_store.create_disposal(
            self.conn, [{"box_id": self.box["id"], "quantity": 15}], reason="hỏng", by="duy")
        self.assertEqual(disposal_store.backfill_timeline_events(self.conn), 1)  # box; chưa xếp vị trí
        self.assertEqual(disposal_store.backfill_timeline_events(self.conn), 0)
        row = self.conn.execute(
            "SELECT action, payload_json FROM audit_events WHERE scope='box' AND thread_id=?",
            (self.box["id"],),
        ).fetchone()
        self.assertEqual(row["action"], "box.disposed")
        self.assertIn(f'"disposal_id":{slip["id"]}', row["payload_json"])


if __name__ == "__main__":
    unittest.main()
