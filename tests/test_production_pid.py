"""Tests Phase 2 product-id cho sản xuất: slip + report_rows trỏ product_id,
sp_name hiển thị = mã hiện hành sau đổi mã, defaults mâm/lượng DB-first
(fallback SP_INFO), dashboard gom theo mã hiện hành."""
from __future__ import annotations

import os
import tempfile
import unittest

from product_store import (
    create_products_table,
    get_product,
    migrate_products_table,
    record_code_change,
    upsert_product,
)
from product_store.schema import _invalidate_products_cache
from production_store.defaults import production_defaults
from production_store.queries import get_slip, list_slips, set_bang, set_sp, upsert_slip
from production_store.report_rows import dashboard, ensure_report_rows_schema
from production_store.schema import create_production_table, migrate_production_table
from utils.db import get_connection


class Base(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        _invalidate_products_cache()
        create_products_table(self.conn)
        migrate_products_table(self.conn)
        create_production_table(self.conn)
        migrate_production_table(self.conn)
        ensure_report_rows_schema(self.conn)
        upsert_product(self.conn, "K10", name="Kẹo 10", prod_mam=3, prod_luong=1200)
        self.pid = get_product(self.conn, "K10")["id"]

    def tearDown(self):
        self.conn.close()
        for ext in ("", "-wal", "-shm"):
            try:
                os.unlink(self.path + ext)
            except FileNotFoundError:
                pass

    def _rename(self, old, new, pid):
        self.conn.execute("UPDATE products SET code = ? WHERE id = ?", (new, pid))
        record_code_change(self.conn, pid, old, new)
        self.conn.commit()
        _invalidate_products_cache()


class SlipById(Base):
    def test_set_sp_stores_pid_and_live_display(self):
        upsert_slip(self.conn, 100, date_code="20260709")
        set_sp(self.conn, 100, "K10", 3, 1200)
        self.assertEqual(get_slip(self.conn, 100)["product_id"], self.pid)
        self._rename("K10", "K10X", self.pid)
        self.assertEqual(get_slip(self.conn, 100)["sp_name"], "K10X")   # mã hiện hành
        self.assertEqual(list_slips(self.conn)[0]["sp_name"], "K10X")

    def test_set_sp_old_code_normalizes(self):
        self._rename("K10", "K10X", self.pid)
        upsert_slip(self.conn, 101, date_code="20260709")
        set_sp(self.conn, 101, "K10", 3, 1200)                          # gõ mã cũ
        slip = get_slip(self.conn, 101)
        self.assertEqual(slip["product_id"], self.pid)
        self.assertEqual(slip["sp_name"], "K10X")

    def test_set_sp_giu_luong_1sp_khi_da_co_bao_cao(self):
        from production_store.wages import ensure_table, set_wage
        ensure_table(self.conn)
        set_wage(self.conn, "K10", 500)
        upsert_product(self.conn, "K20", name="Kẹo 20")
        set_wage(self.conn, "K20", 999)
        upsert_slip(self.conn, 300, date_code="20260709")
        set_sp(self.conn, 300, "K10", 3, 1200)                          # chốt luong_1sp = 500
        self.assertEqual(get_slip(self.conn, 300)["luong_1sp"], 500)
        # phiếu có báo cáo thợ
        set_bang(self.conn, 300, {"product_code": "K10", "date": "9/7/2026",
                                  "rows": [{"name": "Thợ A", "so_gach": 10, "tong_calc": 100}]})
        # đổi SP sau khi có báo cáo → GIỮ luong_1sp cũ (không re-chốt về 999)
        set_sp(self.conn, 300, "K20", 3, 1200)
        slip = get_slip(self.conn, 300)
        self.assertEqual(slip["sp_name"], "K20")
        self.assertEqual(slip["luong_1sp"], 500)

    def test_non_catalog_name_keeps_null_pid(self):
        upsert_slip(self.conn, 102, date_code="20260709")
        set_sp(self.conn, 102, "TÊN TỰ DO", None, None)
        slip = get_slip(self.conn, 102)
        self.assertIsNone(slip["product_id"])
        self.assertEqual(slip["sp_name"], "TÊN TỰ DO")                  # fallback snapshot


class ReportRowsById(Base):
    def test_report_rows_follow_rename(self):
        upsert_slip(self.conn, 200, date_code="20260709")
        set_bang(self.conn, 200, {
            "product_code": "K10", "date": "9/7/2026",
            "rows": [{"name": "Thợ A", "so_gach": 10, "tong_calc": 100}],
        })
        row = self.conn.execute(
            "SELECT product_id, product_code FROM production_report_rows WHERE thread_id=200"
        ).fetchone()
        self.assertEqual(row[0], self.pid)
        self._rename("K10", "K10X", self.pid)
        d = dashboard(self.conn)
        self.assertEqual(d["by_product"][0]["code"], "K10X")            # gom theo mã hiện hành


class Defaults(Base):
    def test_db_first_then_sp_info(self):
        self.assertEqual(production_defaults(self.conn, "K10"), (3, 1200))
        # SP trong danh mục nhưng CHƯA đặt mâm/lượng → fallback SP_INFO (K2L có trong config)
        upsert_product(self.conn, "K2L", name="Kẹo 2L")
        mam, luong = production_defaults(self.conn, "K2L")
        self.assertEqual((mam, luong), (3.5, 720))                      # từ SP_INFO
        # mã cũ vẫn ra defaults của SP
        self._rename("K10", "K10X", self.pid)
        self.assertEqual(production_defaults(self.conn, "K10"), (3, 1200))


if __name__ == "__main__":
    unittest.main()
