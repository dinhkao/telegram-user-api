"""Test phiếu ĐIỀU CHỈNH tồn thùng (inventory_store/adjustments) + ÁP DỤNG kiểm kho
(inventory_store/stocktake_apply): allocation kind='adjustment' không sửa quantity
gốc; guard tồn âm; gỡ phiếu hoàn nguyên; apply delta all-or-nothing, 1 lần/phiếu."""
from __future__ import annotations

import os
import tempfile
import unittest

from inventory_store.adjustments import (create_adjustment, delete_adjustment,
                                         list_adjustments)
from inventory_store.allocations import allocate_picks, create_allocations_table
from inventory_store.queries import add_boxes, get_box
from inventory_store.schema import create_inventory_table, migrate_inventory_table
from inventory_store.stocktakes import (complete_stocktake, create_or_resume_stocktake,
                                        create_stocktake_tables, save_stocktake)
from inventory_store.stocktake_apply import apply_stocktake
from product_store import create_products_table, migrate_products_table, upsert_product
from product_store.schema import _invalidate_products_cache
from utils.db import get_connection


def _remaining(conn, box_id):
    q = float(get_box(conn, box_id)["quantity"])
    used = conn.execute(
        "SELECT COALESCE(SUM(quantity),0) FROM box_allocations WHERE box_id = ?", (box_id,)).fetchone()[0]
    return q - float(used or 0)


class AdjustmentTest(unittest.TestCase):
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
        upsert_product(self.conn, "KEO1", "Kẹo", unit="cây")
        self.box = add_boxes(self.conn, "KEO1", [100])[0]

    def tearDown(self):
        self.conn.close()
        _invalidate_products_cache()
        os.unlink(self.path)

    def test_giam_ton_khong_doi_quantity_goc(self):
        adj, err = create_adjustment(self.conn, self.box["id"], new_remaining=90,
                                     reason="hàng vỡ", by="duy")
        self.assertIsNone(err)
        self.assertEqual(adj["delta"], -10)
        self.assertEqual(adj["old_remaining"], 100)
        self.assertEqual(_remaining(self.conn, self.box["id"]), 90)
        self.assertEqual(float(get_box(self.conn, self.box["id"])["quantity"]), 100)  # gốc GIỮ NGUYÊN
        row = self.conn.execute("SELECT kind, quantity, order_thread_id FROM box_allocations").fetchone()
        self.assertEqual((row["kind"], row["quantity"], row["order_thread_id"]), ("adjustment", 10, adj["id"]))

    def test_tang_ton_va_validate(self):
        adj, err = create_adjustment(self.conn, self.box["id"], new_remaining=120, reason="đếm sót", by="duy")
        self.assertIsNone(err)
        self.assertEqual(_remaining(self.conn, self.box["id"]), 120)
        _, err = create_adjustment(self.conn, self.box["id"], new_remaining=120, reason="x", by="duy")
        self.assertIn("không có gì", err)                              # không đổi
        _, err = create_adjustment(self.conn, self.box["id"], new_remaining=50, reason="", by="duy")
        self.assertIn("lý do", err)                                    # bắt buộc lý do
        _, err = create_adjustment(self.conn, self.box["id"], new_remaining=-5, reason="x", by="duy")
        self.assertIn("≥ 0", err)
        _, err = create_adjustment(self.conn, 999, new_remaining=5, reason="x", by="duy")
        self.assertIn("Không tìm thấy", err)

    def test_go_phieu_hoan_nguyen_va_guard_ton_am(self):
        adj, _ = create_adjustment(self.conn, self.box["id"], new_remaining=120, reason="đếm sót", by="duy")
        # dùng hết 115/120 → gỡ phiếu (−20) sẽ âm → chặn
        allocate_picks(self.conn, [{"box_id": self.box["id"], "quantity": 115}], 777)
        _, err = delete_adjustment(self.conn, adj["id"], by="admin")
        self.assertIn("tồn âm", err)
        # thu hồi bớt → gỡ được, remaining về đúng
        self.conn.execute("DELETE FROM box_allocations WHERE kind='order'")
        self.conn.commit()
        gone, err = delete_adjustment(self.conn, adj["id"], by="admin")
        self.assertIsNone(err)
        self.assertEqual(_remaining(self.conn, self.box["id"]), 100)
        self.assertTrue(list_adjustments(self.conn, box_id=self.box["id"])[0]["deleted_at"])

    # ── ÁP DỤNG kiểm kho ──
    def _make_stocktake(self, counted: float):
        """Tạo vị trí + phiếu kiểm 1 thùng, đếm = counted, chốt phiếu."""
        self.conn.execute("CREATE TABLE IF NOT EXISTS inventory_places (id INTEGER PRIMARY KEY, name TEXT, note TEXT)")
        self.conn.execute("INSERT INTO inventory_places (id, name) VALUES (1, 'Kho A')")
        self.conn.execute("UPDATE inventory_boxes SET place_id = 1 WHERE id = ?", (self.box["id"],))
        self.conn.commit()
        create_stocktake_tables(self.conn)
        st, _ = create_or_resume_stocktake(self.conn, 1, actor="duy")
        item_id = st["items"][0]["id"]
        save_stocktake(self.conn, st["id"], [{"id": item_id, "actual_quantity": counted}], actor="duy")
        slip, err = complete_stocktake(self.conn, st["id"], actor="duy")
        assert err is None, err
        return slip

    def test_apply_stocktake_tao_phieu_dieu_chinh_theo_delta(self):
        st = self._make_stocktake(counted=93)          # sổ sách 100, đếm 93 → delta −7
        slip, err = apply_stocktake(self.conn, st["id"], actor="duy")
        self.assertIsNone(err)
        self.assertEqual(_remaining(self.conn, self.box["id"]), 93)
        res = slip["applied_result"]
        self.assertEqual(res["adjusted"][0]["delta"], -7)
        adjs = list_adjustments(self.conn, stocktake_id=st["id"])
        self.assertEqual(len(adjs), 1)
        self.assertEqual(adjs[0]["source"], "stocktake")
        # áp lần 2 → chặn
        _, err2 = apply_stocktake(self.conn, st["id"], actor="duy")
        self.assertEqual(err2, "already")

    def test_go_le_phieu_sinh_tu_kiem_kho_bi_chan(self):
        st = self._make_stocktake(counted=93)          # delta −7
        apply_stocktake(self.conn, st["id"], actor="duy")
        adj = list_adjustments(self.conn, stocktake_id=st["id"])[0]
        _, err = delete_adjustment(self.conn, adj["id"], by="duy")
        self.assertIsNotNone(err)
        self.assertIn("kiểm kho", err)
        # allocation vẫn còn → tồn không đổi
        self.assertEqual(_remaining(self.conn, self.box["id"]), 93)

    def test_apply_theo_delta_khi_kho_da_bien_dong_hop_le(self):
        st = self._make_stocktake(counted=93)
        # SAU khi chốt, kho xuất thêm 50 cho đơn (biến động HỢP LỆ có sổ)
        allocate_picks(self.conn, [{"box_id": self.box["id"], "quantity": 50}], 888)
        slip, err = apply_stocktake(self.conn, st["id"], actor="duy")
        self.assertIsNone(err)
        # delta −7 cộng dồn: 100 − 50 − 7 = 43 (KHÔNG ép về 93)
        self.assertEqual(_remaining(self.conn, self.box["id"]), 43)

    def test_apply_chan_khi_ton_se_am(self):
        st = self._make_stocktake(counted=40)          # delta −60
        allocate_picks(self.conn, [{"box_id": self.box["id"], "quantity": 95}], 889)  # còn 5
        _, err = apply_stocktake(self.conn, st["id"], actor="duy")
        self.assertIn("tồn sẽ âm", err)
        self.assertEqual(_remaining(self.conn, self.box["id"]), 5)     # không áp gì
        self.assertIsNone(
            self.conn.execute("SELECT applied_at FROM inventory_stocktakes WHERE id = ?", (st["id"],)).fetchone()[0])

    def test_apply_doi_phieu_da_chot(self):
        self.conn.execute("CREATE TABLE IF NOT EXISTS inventory_places (id INTEGER PRIMARY KEY, name TEXT, note TEXT)")
        self.conn.execute("INSERT INTO inventory_places (id, name) VALUES (1, 'Kho A')")
        self.conn.execute("UPDATE inventory_boxes SET place_id = 1 WHERE id = ?", (self.box["id"],))
        self.conn.commit()
        create_stocktake_tables(self.conn)
        st, _ = create_or_resume_stocktake(self.conn, 1, actor="duy")
        _, err = apply_stocktake(self.conn, st["id"], actor="duy")
        self.assertEqual(err, "not_completed")


if __name__ == "__main__":
    unittest.main()
