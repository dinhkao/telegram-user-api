"""Dashboard hao hụt NL phụ (inventory_store.aux_loss): combiner thuần + 1 kịch
bản đầy đủ (sản xuất trong kỳ + châm + 2 lần đếm) với mốc thời gian cố định."""
from __future__ import annotations

import os
import tempfile
import unittest

from product_store import create_products_table, migrate_products_table, upsert_product, get_product
from product_store.schema import _invalidate_products_cache
from recipe_store import create_recipe_table, set_recipe_line
from inventory_store.schema import create_inventory_table, migrate_inventory_table
from inventory_store.allocations import create_allocations_table
from inventory_store.stocktakes import create_stocktake_tables
from inventory_store.aux_loss import aux_loss_periods, combine_material_row
from utils.db import get_connection


class CombineRowTest(unittest.TestCase):
    def test_closed_period_gap(self):
        # đếm trước 100, châm 50, đếm sau 70 → tiêu thụ = 100+50−70 = 80;
        # dùng theo công thức 20 → gap = 60 (mất nhiều hơn định mức).
        r = combine_material_row(used=20, cham=50, prev=100, now=70)
        self.assertEqual((r["consumed"], r["gap"]), (80.0, 60.0))

    def test_open_period_has_no_consumed(self):
        r = combine_material_row(used=12, cham=0, prev=100, now=None)
        self.assertIsNone(r["consumed"])
        self.assertIsNone(r["gap"])
        self.assertEqual(r["used"], 12.0)

    def test_gap_negative_when_used_more_than_drop(self):
        # sụt giảm thực 5 nhưng định mức 8 → gap = −3 (dùng ít hơn định mức / đếm dư).
        r = combine_material_row(used=8, cham=0, prev=50, now=45)
        self.assertEqual(r["gap"], -3.0)


class AuxLossScenarioTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        _invalidate_products_cache()
        create_products_table(self.conn)
        migrate_products_table(self.conn)
        create_recipe_table(self.conn)
        create_inventory_table(self.conn)
        migrate_inventory_table(self.conn)
        create_allocations_table(self.conn)
        create_stocktake_tables(self.conn)

    def tearDown(self):
        self.conn.close()
        _invalidate_products_cache()
        os.unlink(self.path)

    def _seed(self):
        c = self.conn
        upsert_product(c, "SP", "Kẹo thành phẩm")
        upsert_product(c, "TEM", "Tem dán")
        set_recipe_line(c, "SP", "TEM", 2, aux=True)   # 1 cây SP cần 2 TEM (NL phụ)
        tem_id = get_product(c, "TEM")["id"]
        sp_id = get_product(c, "SP")["id"]
        # kho nguyên liệu đang dùng (aux_source)
        cur = c.execute("INSERT INTO inventory_places (name, aux_source) VALUES ('Kho nguyên liệu đang dùng', 1)")
        place_id = cur.lastrowid
        # thùng TEM nằm trong kho (tạo TRƯỚC kỳ → không tính là châm)
        cur = c.execute(
            "INSERT INTO inventory_boxes (product_id, product_code, box_code, quantity, place_id, created_at) "
            "VALUES (?, 'TEM', '001', 100, ?, '2026-07-01 00:00:00')", (tem_id, place_id))
        tem_box = cur.lastrowid
        # thùng THÀNH PHẨM SP tạo TRONG kỳ (source_thread_id != NULL) → dùng = 10×2 = 20 TEM
        c.execute(
            "INSERT INTO inventory_boxes (product_id, product_code, box_code, quantity, source_thread_id, created_at) "
            "VALUES (?, 'SP', 'F1', 10, 999, '2026-07-15 15:00:00')", (sp_id,))
        # CHÂM: chuyển +50 TEM vào thùng trong kho, giờ VN 20:00 = 13:00 UTC (trong kỳ)
        c.execute(
            "INSERT INTO box_allocations (box_id, order_thread_id, quantity, allocated_at, kind) "
            "VALUES (?, 0, -50, '2026-07-15T20:00:00+07:00', 'transfer_in')", (tem_box,))
        # 2 phiếu kiểm kho ĐÃ CHỐT: đếm trước 100, đếm sau 70
        for completed_at, actual in (("2026-07-15 10:00:00", 100), ("2026-07-16 10:00:00", 70)):
            cur = c.execute(
                "INSERT INTO inventory_stocktakes (place_id, place_name, status, completed_at) "
                "VALUES (?, 'Kho nguyên liệu đang dùng', 'completed', ?)", (place_id, completed_at))
            c.execute(
                "INSERT INTO inventory_stocktake_items "
                "(stocktake_id, box_id, box_code, product_code, expected_quantity, actual_quantity) "
                "VALUES (?, ?, '001', 'TEM', ?, ?)", (cur.lastrowid, tem_box, actual, actual))
        c.commit()

    def test_full_period(self):
        self._seed()
        data = aux_loss_periods(self.conn)
        self.assertIsNotNone(data["place"])
        # kỳ ĐÃ CHỐT = kỳ không mở, mới nhất
        closed = [p for p in data["periods"] if not p["open"]]
        self.assertEqual(len(closed), 1)
        rows = closed[0]["rows"]
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["code"], "TEM")
        self.assertEqual(r["used"], 20.0)      # 10 cây SP × 2
        self.assertEqual(r["cham"], 50.0)      # châm transfer_in
        self.assertEqual(r["prev"], 100.0)
        self.assertEqual(r["now"], 70.0)
        self.assertEqual(r["consumed"], 80.0)  # 100 + 50 − 70
        self.assertEqual(r["gap"], 60.0)       # 80 − 20 = hao hụt thật

    def test_no_aux_place(self):
        # chưa chỉ định kho aux_source → báo lỗi rõ, không crash
        upsert_product(self.conn, "SP", "SP")
        data = aux_loss_periods(self.conn)
        self.assertIsNone(data["place"])
        self.assertEqual(data["periods"], [])


if __name__ == "__main__":
    unittest.main()
