from __future__ import annotations

import os
import tempfile
import unittest

from aux_usage_store import (
    aux_usage_by_ingredient,
    create_aux_usage_table,
    record_boxes_aux_usage,
    void_box_aux_usage,
)
from product_store import create_products_table, migrate_products_table, upsert_product
from product_store.schema import _invalidate_products_cache
from recipe_store import create_recipe_table, set_recipe_line
from utils.db import get_connection

_ALL = ("1970-01-01 00:00:00", "2999-01-01 00:00:00")


class AuxUsageTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        _invalidate_products_cache()
        create_products_table(self.conn)
        migrate_products_table(self.conn)
        create_recipe_table(self.conn)
        create_aux_usage_table(self.conn)
        upsert_product(self.conn, "K10", name="Kẹo", unit="cây")
        upsert_product(self.conn, "TEM", name="Tem dán", unit="cái")
        # K10 cần 1.25 TEM/cây làm NGUYÊN LIỆU PHỤ.
        set_recipe_line(self.conn, "K10", "TEM", 1.25, aux=True)
        self.tem_id = self.conn.execute("SELECT id FROM products WHERE code='TEM'").fetchone()["id"]

    def tearDown(self):
        self.conn.close()
        _invalidate_products_cache()
        for ext in ("", "-wal", "-shm"):
            try:
                os.unlink(self.path + ext)
            except FileNotFoundError:
                pass

    def test_record_computes_amount_and_does_not_touch_stock(self):
        n = record_boxes_aux_usage(self.conn, [{"id": 1, "quantity": 100}], "K10", by="Duy")
        self.assertEqual(n, 1)
        usage = aux_usage_by_ingredient(self.conn, *_ALL)
        self.assertAlmostEqual(usage[self.tem_id], 125.0)   # 100 × 1.25
        # KHÔNG có allocation nào (không trừ kho).
        cnt = self.conn.execute("SELECT COUNT(*) FROM box_allocations").fetchone()[0] \
            if self.conn.execute("SELECT name FROM sqlite_master WHERE name='box_allocations'").fetchone() else 0
        self.assertEqual(cnt, 0)

    def test_record_is_idempotent_per_box(self):
        record_boxes_aux_usage(self.conn, [{"id": 1, "quantity": 100}], "K10")
        record_boxes_aux_usage(self.conn, [{"id": 1, "quantity": 80}], "K10")   # ghi lại → cập nhật
        rows = self.conn.execute("SELECT COUNT(*), SUM(amount) FROM aux_usage_ledger").fetchone()
        self.assertEqual(rows[0], 1)            # vẫn 1 dòng
        self.assertAlmostEqual(rows[1], 100.0)  # 80 × 1.25

    def test_void_removes_from_reconciliation(self):
        record_boxes_aux_usage(self.conn, [{"id": 7, "quantity": 40}], "K10")
        self.assertTrue(aux_usage_by_ingredient(self.conn, *_ALL))
        voided = void_box_aux_usage(self.conn, 7, by="Duy")
        self.assertEqual(voided, 1)
        self.assertEqual(aux_usage_by_ingredient(self.conn, *_ALL), {})   # đã void → không tính

    def test_no_aux_recipe_records_nothing(self):
        upsert_product(self.conn, "X9", name="Không công thức", unit="cây")
        n = record_boxes_aux_usage(self.conn, [{"id": 2, "quantity": 50}], "X9")
        self.assertEqual(n, 0)
