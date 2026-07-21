"""Test quy cách đóng gói cấu hình được: normalize (ép kiểu/chuẩn hoá) + parser
hoá đơn (order_store.free_text) đọc đúng cấu hình từ settings_store."""
from __future__ import annotations

import os
import tempfile
import unittest

from order_store.free_text import parse_invoice_free_text
from order_store.quy_cach import (
    DEFAULTS,
    bich_qty,
    invalidate_cache,
    normalize,
    thung_qty,
)
from product_store import create_products_table, migrate_products_table, upsert_product
from product_store.schema import _invalidate_products_cache
from settings_store import set_value
from utils.db import get_connection


class Normalize(unittest.TestCase):
    def test_empty_gives_defaults(self):
        cfg = normalize({})
        self.assertEqual(cfg["thung_base"], 50)
        self.assertEqual(cfg["bich_base"], 10)
        self.assertEqual(cfg["thung_overrides"]["DM50"], 100)
        self.assertEqual(cfg["bich_overrides"]["KDDT"], 3)
        self.assertEqual(cfg["dm180_loc"], 12)

    def test_bad_values_fall_back(self):
        cfg = normalize({"thung_base": 0, "bich_base": "abc", "dm180_loc": -5})
        self.assertEqual(cfg["thung_base"], 50)
        self.assertEqual(cfg["bich_base"], 10)
        self.assertEqual(cfg["dm180_loc"], 12)

    def test_overrides_replace_and_uppercase(self):
        cfg = normalize({"thung_overrides": {"abc": 7, "BAD": 0, "x": "no"}})
        self.assertEqual(cfg["thung_overrides"], {"ABC": 7})   # BAD(0)+x(non-int) rớt, key in hoa
        self.assertEqual(cfg["bich_overrides"], DEFAULTS["bich_overrides"])  # thiếu → bảng mặc định

    def test_helpers(self):
        cfg = normalize({"thung_base": 60, "thung_overrides": {"K": 8}})
        self.assertEqual(thung_qty("K", cfg), 8)
        self.assertEqual(thung_qty("OTHER", cfg), 60)
        self.assertEqual(bich_qty("KDDT", cfg), 3)


class Integration(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        _invalidate_products_cache()
        invalidate_cache()
        create_products_table(self.conn)
        migrate_products_table(self.conn)
        for c in ("K10", "DM180", "KDDT"):
            upsert_product(self.conn, c, name=c)
        self.conn.commit()

    def tearDown(self):
        invalidate_cache()
        self.conn.close()
        for ext in ("", "-wal", "-shm"):
            try:
                os.unlink(self.path + ext)
            except FileNotFoundError:
                pass

    def _parse(self, text):
        invalidate_cache()   # bỏ cache TTL để đọc cấu hình vừa lưu
        return parse_invoice_free_text(self.conn, text)

    def test_default_bich_base(self):
        self.assertEqual(self._parse("K10 2b")[0]["sl"], 20)   # 2 bịch × 10

    def test_custom_bich_base(self):
        set_value("parse_quy_cach", normalize({"bich_base": 25}), conn=self.conn)
        self.assertEqual(self._parse("K10 2b")[0]["sl"], 50)   # 2 × 25

    def test_custom_thung_override(self):
        set_value("parse_quy_cach", normalize({"thung_overrides": {"K10": 7}}), conn=self.conn)
        self.assertEqual(self._parse("K10 3t")[0]["sl"], 21)   # 3 × 7

    def test_dm180_loc_configurable(self):
        self.assertEqual(self._parse("DM180 2 lốc")[0]["sl"], 24)   # mặc định 2 × 12
        set_value("parse_quy_cach", normalize({"dm180_loc": 6}), conn=self.conn)
        self.assertEqual(self._parse("DM180 2 lốc")[0]["sl"], 12)   # 2 × 6


if __name__ == "__main__":
    unittest.main()
