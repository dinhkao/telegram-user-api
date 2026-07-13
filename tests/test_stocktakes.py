from __future__ import annotations

import os
import tempfile
import unittest

from inventory_store.allocations import allocate_picks, create_allocations_table
from inventory_store.queries import add_boxes, add_place
from inventory_store.schema import create_inventory_table, migrate_inventory_table
from inventory_store.stocktakes import (
    complete_stocktake,
    create_or_resume_stocktake,
    get_stocktake,
    save_stocktake,
)
from product_store import create_products_table, migrate_products_table, upsert_product
from product_store.schema import _invalidate_products_cache
from utils.db import get_connection


class StocktakeStoreTest(unittest.TestCase):
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
        upsert_product(self.conn, "K10", name="Kẹo", unit="cây")
        self.place = add_place(self.conn, "Kho A")
        self.boxes = add_boxes(self.conn, "K10", [50, 30], place_id=self.place["id"])
        allocate_picks(self.conn, [{"box_id": self.boxes[0]["id"], "quantity": 10}], 1001)

    def tearDown(self):
        self.conn.close()
        _invalidate_products_cache()
        for ext in ("", "-wal", "-shm"):
            try:
                os.unlink(self.path + ext)
            except FileNotFoundError:
                pass

    def test_create_captures_remaining_and_resumes_draft(self):
        slip, resumed = create_or_resume_stocktake(self.conn, self.place["id"], actor="Duy")
        self.assertFalse(resumed)
        self.assertEqual([i["expected_quantity"] for i in slip["items"]], [40, 30])
        self.assertEqual(slip["summary"]["expected_total"], 70)

        same, resumed = create_or_resume_stocktake(self.conn, self.place["id"], actor="Khác")
        self.assertTrue(resumed)
        self.assertEqual(same["id"], slip["id"])

    def test_snapshot_does_not_drift_when_inventory_changes(self):
        slip, _ = create_or_resume_stocktake(self.conn, self.place["id"])
        allocate_picks(self.conn, [{"box_id": self.boxes[1]["id"], "quantity": 5}], 1002)
        after = get_stocktake(self.conn, slip["id"])
        self.assertEqual([i["expected_quantity"] for i in after["items"]], [40, 30])

    def test_save_and_complete_report_difference(self):
        slip, _ = create_or_resume_stocktake(self.conn, self.place["id"])
        first, second = slip["items"]
        partial, err = save_stocktake(self.conn, slip["id"], [
            {"id": first["id"], "actual_quantity": 38, "note": "thiếu 2"},
        ], actor="Lan")
        self.assertIsNone(err)
        self.assertEqual(partial["summary"]["counted_count"], 1)
        self.assertEqual(partial["updated_by"], "Lan")
        self.assertIsNone(partial["summary"]["difference_total"])
        done, err = complete_stocktake(self.conn, slip["id"], actor="Duy")
        self.assertIsNone(done)
        self.assertEqual(err, "incomplete")

        saved, err = save_stocktake(self.conn, slip["id"], [
            {"id": second["id"], "actual_quantity": 35},
        ], note="Kiểm ca tối")
        self.assertIsNone(err)
        done, err = complete_stocktake(self.conn, slip["id"], actor="Duy")
        self.assertIsNone(err)
        self.assertEqual(done["status"], "completed")
        self.assertEqual(done["summary"]["expected_total"], 70)
        self.assertEqual(done["summary"]["actual_total"], 73)
        self.assertEqual(done["summary"]["difference_total"], 3)
        self.assertEqual(done["summary"]["deviation_count"], 2)
        self.assertEqual(done["completed_by"], "Duy")
        self.assertEqual(done["updated_by"], "Duy")

        fresh, resumed = create_or_resume_stocktake(self.conn, self.place["id"])
        self.assertFalse(resumed)
        self.assertNotEqual(fresh["id"], done["id"])

    def test_rejects_negative_actual(self):
        slip, _ = create_or_resume_stocktake(self.conn, self.place["id"])
        result, err = save_stocktake(self.conn, slip["id"], [
            {"id": slip["items"][0]["id"], "actual_quantity": -1},
        ])
        self.assertIsNone(result)
        self.assertEqual(err, "invalid")


if __name__ == "__main__":
    unittest.main()
