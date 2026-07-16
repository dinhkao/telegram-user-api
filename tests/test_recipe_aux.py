"""NGUYÊN LIỆU PHỤ (product_recipes.aux): lọc list/needs theo loại, upsert đổi
chính↔phụ không tạo dòng đôi. Gate nhập kho SX dùng recipe_needs(aux=...)."""
from __future__ import annotations

import os
import tempfile
import unittest

from product_store import create_products_table, migrate_products_table, upsert_product
from product_store.schema import _invalidate_products_cache
from recipe_store import create_recipe_table, list_recipe, set_recipe_line, recipe_needs
from utils.db import get_connection


class RecipeAuxTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        _invalidate_products_cache()
        create_products_table(self.conn)
        migrate_products_table(self.conn)
        create_recipe_table(self.conn)
        for code in ("KEO1", "TEM1", "HOP1"):
            upsert_product(self.conn, code, code)

    def tearDown(self):
        self.conn.close()
        _invalidate_products_cache()
        os.unlink(self.path)

    def test_set_and_filter_by_aux(self):
        assert set_recipe_line(self.conn, "KEO1", "HOP1", 0.5) is not None            # NL chính
        line = set_recipe_line(self.conn, "KEO1", "TEM1", 2, aux=True)                # NL phụ
        self.assertEqual(line["aux"], 1)
        allr = list_recipe(self.conn, "KEO1")
        self.assertEqual({(r["ingredient_code"], r["aux"]) for r in allr},
                         {("HOP1", 0), ("TEM1", 1)})
        self.assertEqual([r["ingredient_code"] for r in list_recipe(self.conn, "KEO1", aux=True)], ["TEM1"])
        self.assertEqual([r["ingredient_code"] for r in list_recipe(self.conn, "KEO1", aux=False)], ["HOP1"])
        # nhu cầu theo loại: aux=True chỉ NL phụ, aux=False chỉ chính, None = cả hai
        self.assertEqual(recipe_needs(self.conn, "KEO1", 10, aux=True), [{"code": "TEM1", "amount": 20}])
        self.assertEqual(recipe_needs(self.conn, "KEO1", 10, aux=False), [{"code": "HOP1", "amount": 5}])
        self.assertEqual(len(recipe_needs(self.conn, "KEO1", 10)), 2)

    def test_ratio_unit_converts_to_base(self):
        # Nhập tỉ lệ theo ĐƠN VỊ QUY ĐỔI (1 Thùng = 30 gốc) → DB lưu ratio GỐC
        # (needs/gate không đổi) + snapshot ratio_unit/ratio_factor để hiển thị.
        line = set_recipe_line(self.conn, "KEO1", "TEM1", 2, aux=True,
                               ratio_unit="Thùng", ratio_factor=30)
        self.assertEqual(line["ratio"], 60.0)
        self.assertEqual((line["ratio_unit"], line["ratio_factor"]), ("Thùng", 30.0))
        self.assertEqual(recipe_needs(self.conn, "KEO1", 2, aux=True),
                         [{"code": "TEM1", "amount": 120}])
        # factor xấu → rơi phần unit, ratio hiểu theo gốc
        line2 = set_recipe_line(self.conn, "KEO1", "HOP1", 5, ratio_unit="Kiện", ratio_factor=0)
        self.assertEqual(line2["ratio"], 5.0)
        self.assertIsNone(line2["ratio_unit"])

    def test_aux_required_flag_roundtrip(self):
        # Hồi quy: _COLS từng thiếu aux_required → get_product không trả cờ,
        # API luôn coi là bật, toggle ở RecipeEditor bị đè ngược lại.
        from product_store import get_product
        self.assertTrue(get_product(self.conn, "KEO1")["aux_required"])   # mặc định BẬT
        upsert_product(self.conn, "KEO1", aux_required=False)
        self.assertFalse(get_product(self.conn, "KEO1")["aux_required"])
        upsert_product(self.conn, "KEO1", aux_required=True)
        self.assertTrue(get_product(self.conn, "KEO1")["aux_required"])

    def test_upsert_flips_kind_without_duplicate(self):
        set_recipe_line(self.conn, "KEO1", "TEM1", 1)                 # chính
        line = set_recipe_line(self.conn, "KEO1", "TEM1", 3, aux=True)   # đổi thành phụ
        self.assertEqual((line["ratio"], line["aux"]), (3.0, 1))
        rows = list_recipe(self.conn, "KEO1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["aux"], 1)


if __name__ == "__main__":
    unittest.main()
