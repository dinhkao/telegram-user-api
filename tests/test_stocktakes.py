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
    resync_stocktake,
    save_stocktake,
    void_stocktake,
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

    def test_aux_source_place_includes_zero_stock_boxes(self):
        # Kho aux_source: thùng sổ=0 (đã trừ hết) VẪN vào phiếu để đếm hàng thực còn.
        from inventory_store.queries import set_place_aux_source
        aux = add_place(self.conn, "Kho nguyên liệu đang dùng")
        set_place_aux_source(self.conn, aux["id"], True)
        boxes = add_boxes(self.conn, "K10", [20, 30], place_id=aux["id"])
        allocate_picks(self.conn, [{"box_id": boxes[0]["id"], "quantity": 20}], 2001)  # sổ về 0
        slip, _ = create_or_resume_stocktake(self.conn, aux["id"], actor="Duy")
        # Cả 2 thùng có mặt, thùng cạn expected=0 (trước đây bị loại → nay đếm được).
        self.assertEqual(sorted(i["expected_quantity"] for i in slip["items"]), [0, 30])

    def test_non_aux_place_excludes_zero_stock_boxes(self):
        # Kho thường: thùng sổ=0 KHÔNG vào phiếu (toàn hệ nhiều thùng rỗng, tránh loạn).
        boxes = add_boxes(self.conn, "K10", [15], place_id=self.place["id"])
        allocate_picks(self.conn, [{"box_id": boxes[0]["id"], "quantity": 15}], 2002)  # sổ về 0
        slip, _ = create_or_resume_stocktake(self.conn, self.place["id"], actor="Duy")
        # 2 thùng gốc (40, 30) còn tồn; thùng vừa cạn KHÔNG có mặt.
        self.assertEqual(sorted(i["expected_quantity"] for i in slip["items"]), [30, 40])

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

    # ── Biến động kho sau khi tạo phiếu → cờ lỗi thời + chặn chốt + resync/void ──
    def _disable_box(self, box_id):
        self.conn.execute("UPDATE inventory_boxes SET disabled = 1 WHERE id = ?", (box_id,))
        self.conn.commit()

    def test_fresh_slip_not_stale(self):
        slip, _ = create_or_resume_stocktake(self.conn, self.place["id"])
        self.assertFalse(slip["stale"]["changed"])
        self.assertEqual(slip["stale"]["adjusted"], [])

    def test_stale_when_box_remaining_changes(self):
        slip, _ = create_or_resume_stocktake(self.conn, self.place["id"])
        allocate_picks(self.conn, [{"box_id": self.boxes[0]["id"], "quantity": 5}], 2001)
        after = get_stocktake(self.conn, slip["id"])
        self.assertTrue(after["stale"]["changed"])
        self.assertEqual([a["box_id"] for a in after["stale"]["adjusted"]], [self.boxes[0]["id"]])
        self.assertEqual(after["stale"]["adjusted"][0]["expected"], 40)
        self.assertEqual(after["stale"]["adjusted"][0]["current"], 35)
        # Snapshot KHÔNG trôi — expected vẫn cố định.
        self.assertEqual([i["expected_quantity"] for i in after["items"]], [40, 30])

    def test_stale_when_new_box_added(self):
        slip, _ = create_or_resume_stocktake(self.conn, self.place["id"])
        add_boxes(self.conn, "K10", [12], place_id=self.place["id"])
        after = get_stocktake(self.conn, slip["id"])
        self.assertTrue(after["stale"]["changed"])
        self.assertEqual(len(after["stale"]["added"]), 1)
        self.assertEqual(after["stale"]["added"][0]["remaining"], 12)

    def test_stale_when_box_disabled(self):
        slip, _ = create_or_resume_stocktake(self.conn, self.place["id"])
        self._disable_box(self.boxes[1]["id"])
        after = get_stocktake(self.conn, slip["id"])
        self.assertTrue(after["stale"]["changed"])
        self.assertEqual([r["box_id"] for r in after["stale"]["removed"]], [self.boxes[1]["id"]])

    def test_complete_blocked_when_stale(self):
        slip, _ = create_or_resume_stocktake(self.conn, self.place["id"])
        for it in slip["items"]:
            save_stocktake(self.conn, slip["id"], [{"id": it["id"], "actual_quantity": it["expected_quantity"]}])
        allocate_picks(self.conn, [{"box_id": self.boxes[0]["id"], "quantity": 5}], 2002)
        done, err = complete_stocktake(self.conn, slip["id"], actor="Duy")
        self.assertEqual(err, "stale")
        self.assertTrue(done["stale"]["changed"])          # payload trả về mang chi tiết
        self.assertEqual(get_stocktake(self.conn, slip["id"])["status"], "draft")  # chưa chốt

    def test_resync_updates_expected_keeps_actuals_adds_removes(self):
        slip, _ = create_or_resume_stocktake(self.conn, self.place["id"])
        first = slip["items"][0]
        save_stocktake(self.conn, slip["id"], [{"id": first["id"], "actual_quantity": 38, "note": "đếm rồi"}])
        allocate_picks(self.conn, [{"box_id": self.boxes[0]["id"], "quantity": 5}], 2003)  # box0 40→35
        new = add_boxes(self.conn, "K10", [12], place_id=self.place["id"])                 # thùng mới
        self._disable_box(self.boxes[1]["id"])                                             # box1 rời

        resynced, err = resync_stocktake(self.conn, slip["id"], actor="Lan")
        self.assertIsNone(err)
        self.assertFalse(resynced["stale"]["changed"])
        by_box = {i["box_id"]: i for i in resynced["items"]}
        self.assertEqual(by_box[self.boxes[0]["id"]]["expected_quantity"], 35)   # đồng bộ số mới
        self.assertEqual(by_box[self.boxes[0]["id"]]["actual_quantity"], 38)     # GIỮ số đã đếm
        self.assertEqual(by_box[self.boxes[0]["id"]]["note"], "đếm rồi")
        self.assertNotIn(self.boxes[1]["id"], by_box)                            # thùng rời bị bỏ
        self.assertIn(new[0]["id"], by_box)                                      # thùng mới thêm vào
        self.assertIsNone(by_box[new[0]["id"]]["actual_quantity"])
        self.assertEqual(by_box[new[0]["id"]]["expected_quantity"], 12)
        self.assertEqual(resynced["updated_by"], "Lan")

    def test_void_frees_place_for_new_draft(self):
        slip, _ = create_or_resume_stocktake(self.conn, self.place["id"])
        voided, err = void_stocktake(self.conn, slip["id"], actor="Duy")
        self.assertIsNone(err)
        self.assertEqual(voided["status"], "voided")
        fresh, resumed = create_or_resume_stocktake(self.conn, self.place["id"])
        self.assertFalse(resumed)                        # KHÔNG resume phiếu đã huỷ
        self.assertNotEqual(fresh["id"], slip["id"])

    def test_cannot_void_completed(self):
        slip, _ = create_or_resume_stocktake(self.conn, self.place["id"])
        for it in slip["items"]:
            save_stocktake(self.conn, slip["id"], [{"id": it["id"], "actual_quantity": it["expected_quantity"]}])
        complete_stocktake(self.conn, slip["id"], actor="Duy")
        res, err = void_stocktake(self.conn, slip["id"], actor="Duy")
        self.assertIsNone(res)
        self.assertEqual(err, "completed")


if __name__ == "__main__":
    unittest.main()


class StocktakeCountUnitTest(unittest.TestCase):
    """ĐƠN VỊ BẮT BUỘC khi kiểm kho (vai 📋 — docs/plan-don-vi-hang-hoa.md):
    snapshot (tên, factor) từng dòng lúc tạo; nhập N kiện + M lẻ → actual quy về
    gốc, lưu số thô; vai = đơn vị gốc (factor 1) → không stamp (hành vi cũ)."""

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
        from product_store.queries import get_product
        from product_store import units as pu
        pid = get_product(self.conn, "K10")["id"]
        u, _ = pu.add_unit(self.conn, pid, "Thùng", 30, "cây")
        upsert_product(self.conn, "K10", stocktake_unit_id=u["id"])
        self.place = add_place(self.conn, "Kho A")
        self.boxes = add_boxes(self.conn, "K10", [85], place_id=self.place["id"])

    def tearDown(self):
        self.conn.close()
        _invalidate_products_cache()
        for ext in ("", "-wal", "-shm"):
            try:
                os.unlink(self.path + ext)
            except FileNotFoundError:
                pass

    def test_snapshot_va_nhap_kep(self):
        slip, _ = create_or_resume_stocktake(self.conn, self.place["id"], actor="Duy")
        it = slip["items"][0]
        self.assertEqual(it["count_unit_name"], "Thùng")
        self.assertEqual(it["count_unit_factor"], 30.0)
        # đếm 2 Thùng + 25 lẻ → actual = 85 (đơn vị gốc), số thô giữ nguyên
        slip, err = save_stocktake(self.conn, slip["id"],
                                   [{"id": it["id"], "counted_bulk": 2, "counted_loose": 25}])
        self.assertIsNone(err)
        it = slip["items"][0]
        self.assertEqual(it["actual_quantity"], 85.0)
        self.assertEqual(it["counted_bulk"], 2.0)
        self.assertEqual(it["counted_loose"], 25.0)
        # cả 2 ô trống = chưa đếm
        slip, err = save_stocktake(self.conn, slip["id"],
                                   [{"id": it["id"], "counted_bulk": "", "counted_loose": ""}])
        self.assertIsNone(err)
        self.assertIsNone(slip["items"][0]["actual_quantity"])

    def test_doi_vai_sau_khi_tao_khong_anh_huong(self):
        slip, _ = create_or_resume_stocktake(self.conn, self.place["id"])
        upsert_product(self.conn, "K10", stocktake_unit_id=None)   # gỡ vai sau khi chụp
        got = get_stocktake(self.conn, slip["id"])
        self.assertEqual(got["items"][0]["count_unit_factor"], 30.0)   # snapshot giữ nguyên

    def test_vai_don_vi_goc_khong_stamp(self):
        upsert_product(self.conn, "K10", stocktake_unit_id=0)   # ép đếm đơn vị gốc
        # phải xoá nháp cũ nếu có (mỗi test DB riêng nên không cần) — tạo mới
        slip, _ = create_or_resume_stocktake(self.conn, self.place["id"])
        self.assertIsNone(slip["items"][0]["count_unit_name"])
