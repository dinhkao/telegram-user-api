"""Test server_app.purchase_goods.apply_purchase_receipt — nhập kho hàng mua về:
nhập vào thùng có sẵn (allocation ÂM 'purchase_in') / tạo thùng mới (source_purchase_id);
guard đã-nhập; khoá không có trong hàng trả: KHÔNG có action dispose."""
from __future__ import annotations

import os
import tempfile
import unittest

import purchase_store
from inventory_store.allocations import create_allocations_table
from inventory_store.queries import add_boxes, get_box, list_boxes
from inventory_store.schema import create_inventory_table, migrate_inventory_table
from product_store import create_products_table, migrate_products_table, upsert_product
from product_store.schema import _invalidate_products_cache
from server_app.purchase_goods import apply_purchase_receipt
from utils.db import get_connection


class PurchaseGoodsTest(unittest.TestCase):
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
        purchase_store.ensure_purchases_schema(self.conn)
        upsert_product(self.conn, "KEO1", "Kẹo", unit="cây")
        self.box = add_boxes(self.conn, "KEO1", [100])[0]
        self.pu = purchase_store.add_purchase(
            self.conn, 1, [{"sp": "KEO1", "sl": 20, "price": 5000}], 100000, by="duy")

    def tearDown(self):
        self.conn.close()
        _invalidate_products_cache()
        os.unlink(self.path)

    def _rem(self, box_id):
        q = float(get_box(self.conn, box_id)["quantity"])
        used = self.conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM box_allocations WHERE box_id = ?", (box_id,)).fetchone()[0]
        return q - float(used or 0)

    def test_restock_existing_negative_purchase_in_allocation(self):
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 20, "action": "restock_existing", "box_id": self.box["id"]}],
            actor="lan")
        self.assertIsNone(err)
        self.assertEqual(float(get_box(self.conn, self.box["id"])["quantity"]), 100)  # quantity GỐC giữ nguyên
        self.assertEqual(self._rem(self.box["id"]), 120)                              # remaining TĂNG 20
        row = self.conn.execute(
            "SELECT kind, quantity, order_thread_id FROM box_allocations WHERE box_id = ?",
            (self.box["id"],)).fetchone()
        self.assertEqual(row["kind"], "purchase_in")
        self.assertEqual(row["quantity"], -20)
        self.assertEqual(row["order_thread_id"], self.pu["id"])
        got = purchase_store.get_purchase(self.conn, self.pu["id"])
        self.assertIsNotNone(got["goods_handled_at"])
        self.assertEqual(len(got["goods_result"]["restocked_existing"]), 1)

    def test_restock_new_creates_box_with_source_purchase_id(self):
        before = len(list_boxes(self.conn))
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 20, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err)
        self.assertEqual(len(list_boxes(self.conn)), before + 1)
        new_id = extra["result"]["restocked_new"][0]["box_id"]
        b = get_box(self.conn, new_id)
        self.assertEqual(float(b["quantity"]), 20)
        self.assertEqual(b["source_purchase_id"], self.pu["id"])
        self.assertIn(f"#{self.pu['id']}", b["note"])

    def test_restock_new_count_creates_multiple_boxes(self):
        # count = số thùng giống nhau (như nhập thùng phiếu SX); mỗi thùng `quantity` hàng.
        before = len(list_boxes(self.conn))
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 5, "count": 4, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err)
        self.assertEqual(len(list_boxes(self.conn)), before + 4)   # 4 thùng mới
        news = extra["result"]["restocked_new"]
        self.assertEqual(len(news), 4)                             # 1 entry / thùng
        for e in news:
            self.assertEqual(float(get_box(self.conn, e["box_id"])["quantity"]), 5)
        self.assertEqual(len(set(e["box_id"] for e in news)), 4)   # 4 thùng riêng biệt

    def test_second_apply_blocked(self):
        _, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 20, "action": "restock_existing", "box_id": self.box["id"]}],
            actor="lan")
        self.assertIsNone(err)
        _, err2 = apply_purchase_receipt(self.conn, self.pu["id"], [], actor="hai")
        self.assertEqual(err2, "already")
        self.assertEqual(len(list_boxes(self.conn)), 1)   # không tạo thêm thùng

    def test_apply_blocked_when_not_enough(self):
        # Rule chốt: nhập ĐỦ mọi mã theo phiếu mới chốt được — thiếu → lỗi, rollback cả lô.
        before = len(list_boxes(self.conn))
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 15, "action": "restock_new"}], actor="lan")
        self.assertIsNone(extra)
        self.assertIn("Chưa nhập đủ", err)
        self.assertEqual(len(list_boxes(self.conn)), before)   # không ghi dòng nào
        self.assertIsNone(purchase_store.get_purchase(self.conn, self.pu["id"])["goods_handled_at"])

    def test_draft_receipt_carries_sp_id(self):
        # Client khớp dòng phiếu ↔ đã-nhập theo sp_id — mã SP đổi tên giữa chừng vẫn khớp.
        from product_store import resolve_code
        from server_app.purchase_goods import receive_purchase_lines, _draft_receipt
        _, err = receive_purchase_lines(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 5, "action": "restock_new"},
             {"sp": "KEO1", "quantity": 3, "action": "restock_existing", "box_id": self.box["id"]}],
            actor="lan")
        self.assertIsNone(err)
        pid = resolve_code(self.conn, "KEO1")["id"]
        d = _draft_receipt(self.conn, self.pu["id"])
        self.assertEqual(d["new"][0]["sp_id"], pid)
        self.assertEqual(d["existing"][0]["sp_id"], pid)

    def test_batch_draft_status(self):
        # Badge 'nhập dở' dashboard: False khi chưa nhập gì, True khi có thùng/
        # allocation nhập dở (cả 2 nhánh new + existing).
        from purchase_store import batch_draft_status
        from server_app.purchase_goods import receive_purchase_lines
        self.assertEqual(batch_draft_status(self.conn, [self.pu["id"]]), {self.pu["id"]: False})
        _, err = receive_purchase_lines(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 3, "action": "restock_existing", "box_id": self.box["id"]}],
            actor="lan")
        self.assertIsNone(err)
        self.assertTrue(batch_draft_status(self.conn, [self.pu["id"]])[self.pu["id"]])
        _, err2 = receive_purchase_lines(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 5, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err2)
        self.assertTrue(batch_draft_status(self.conn, [self.pu["id"]])[self.pu["id"]])

    def test_confirm_blocked_until_enough(self):
        from server_app.purchase_goods import confirm_purchase_receipt
        _, err = confirm_purchase_receipt(self.conn, self.pu["id"], actor="lan")
        self.assertIn("Chưa nhập đủ", err)
        self.assertIsNone(purchase_store.get_purchase(self.conn, self.pu["id"])["goods_handled_at"])

    def test_invalid_lines_rejected_without_partial_apply(self):
        before = len(list_boxes(self.conn))
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "", "quantity": 5, "action": "restock_new"},                       # thiếu mã
             {"sp": "KEO1", "quantity": 0, "action": "restock_new"},                   # số ≤ 0
             {"sp": "KEO1", "quantity": 3, "action": "restock_existing", "box_id": 999},  # thùng không có
             {"sp": "KEO1", "quantity": 7, "action": "skip"},
             {"sp": "KEO1", "quantity": 2, "action": "dispose"},                       # KHÔNG hỗ trợ với hàng mua
             {"sp": "KEO1", "quantity": 4, "action": "restock_new"}], actor="lan")
        self.assertIsNone(extra)
        self.assertIn("Thiếu mã", err)
        self.assertEqual(len(list_boxes(self.conn)), before)
        self.assertIsNone(purchase_store.get_purchase(self.conn, self.pu["id"])["goods_handled_at"])

    def test_restock_cannot_exceed_purchase_quantity(self):
        before = len(list_boxes(self.conn))
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 30, "count": 3, "action": "restock_new"}], actor="lan")
        self.assertIsNone(extra)
        self.assertIn("vượt số trên phiếu", err)
        self.assertEqual(len(list_boxes(self.conn)), before)
        self.assertIsNone(purchase_store.get_purchase(self.conn, self.pu["id"])["goods_handled_at"])

    def test_restock_existing_requires_matching_product_box(self):
        upsert_product(self.conn, "KEO2", "Kẹo khác", unit="cây")
        other = add_boxes(self.conn, "KEO2", [100])[0]
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 5, "action": "restock_existing", "box_id": other["id"]}],
            actor="lan")
        self.assertIsNone(extra)
        self.assertIn("không phải KEO1", err)
        rows = self.conn.execute("SELECT * FROM box_allocations WHERE box_id = ?", (other["id"],)).fetchall()
        self.assertEqual(rows, [])
        self.assertIsNone(purchase_store.get_purchase(self.conn, self.pu["id"])["goods_handled_at"])

    def test_restock_existing_rejects_disabled_box(self):
        self.conn.execute("UPDATE inventory_boxes SET disabled = 1 WHERE id = ?", (self.box["id"],))
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 5, "action": "restock_existing", "box_id": self.box["id"]}],
            actor="lan")
        self.assertIsNone(extra)
        self.assertIn("vô hiệu", err)
        self.assertIsNone(purchase_store.get_purchase(self.conn, self.pu["id"])["goods_handled_at"])

    def test_mark_deleted_boxes_flags_removed_box(self):
        from inventory_store.queries import delete_box
        from server_app.purchase_goods_view import mark_deleted_boxes
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 20, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err)
        new_id = extra["result"]["restocked_new"][0]["box_id"]
        row = mark_deleted_boxes(self.conn, purchase_store.get_purchase(self.conn, self.pu["id"]))
        self.assertNotIn("box_deleted", row["goods_result"]["restocked_new"][0])  # thùng còn → không cờ
        delete_box(self.conn, new_id)   # admin xoá hẳn thùng
        row2 = mark_deleted_boxes(self.conn, purchase_store.get_purchase(self.conn, self.pu["id"]))
        self.assertTrue(row2["goods_result"]["restocked_new"][0]["box_deleted"])

    # ── HỦY CHỐT nhập kho (undo_purchase_receipt) ──
    def _receive_both(self):
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 10, "action": "restock_existing", "box_id": self.box["id"]},
             {"sp": "KEO1", "quantity": 10, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err)
        return extra["result"]["restocked_new"][0]["box_id"]

    def test_undo_receipt_full_revert(self):
        from server_app.purchase_goods import undo_purchase_receipt
        new_id = self._receive_both()
        info, err = undo_purchase_receipt(self.conn, self.pu["id"])
        self.assertIsNone(err)
        self.assertIn(new_id, info["retained_boxes"])
        self.assertIsNotNone(get_box(self.conn, new_id))         # thùng mới giữ nguyên
        self.assertEqual(float(get_box(self.conn, new_id)["quantity"]), 10)
        self.assertEqual(self._rem(self.box["id"]), 100)         # thùng có sẵn về như cũ
        got = purchase_store.get_purchase(self.conn, self.pu["id"])
        self.assertIsNone(got["goods_handled_at"])               # phiếu mở khoá lại
        self.assertIsNone(got["goods_result"])                   # trạng thái đang nhập derive live
        # nhập kho LẠI được sau khi hủy chốt (thùng 10 giữ lại + 10 mới = đủ 20)
        extra2, err2 = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 10, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err2)
        self.assertEqual(len(extra2["result"]["restocked_new"]), 2)
        self.assertEqual(sum(e["quantity"] for e in extra2["result"]["restocked_new"]), 20)

    def test_undo_allows_deleting_one_box_then_adding_more(self):
        from inventory_store.queries import delete_box
        from server_app.purchase_goods import undo_purchase_receipt
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 5, "count": 4, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err)
        ids = [e["box_id"] for e in extra["result"]["restocked_new"]]

        info, undo_err = undo_purchase_receipt(self.conn, self.pu["id"])
        self.assertIsNone(undo_err)
        self.assertEqual(info["retained_boxes"], ids)
        delete_box(self.conn, ids[0])

        extra2, apply_err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 5, "action": "restock_new"}], actor="lan")
        self.assertIsNone(apply_err)
        current = extra2["result"]["restocked_new"]
        self.assertEqual(len(current), 4)
        self.assertNotIn(ids[0], [e["box_id"] for e in current])
        self.assertTrue(all(get_box(self.conn, e["box_id"]) for e in current))

    def test_receive_then_confirm_incremental(self):
        # Flow MỚI như xuất kho đơn: ghi từng đợt khi phiếu mở → đủ thì chốt.
        from server_app.purchase_goods import receive_purchase_lines, confirm_purchase_receipt
        extra, err = receive_purchase_lines(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 5, "count": 2, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err)
        self.assertEqual(len(extra["touched_boxes"]), 2)
        got = purchase_store.get_purchase(self.conn, self.pu["id"])
        self.assertIsNone(got["goods_handled_at"])               # CHƯA chốt, phiếu vẫn mở
        # đợt 2: cộng vào thùng có sẵn
        _, err2 = receive_purchase_lines(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 6, "action": "restock_existing", "box_id": self.box["id"]}],
            actor="lan")
        self.assertIsNone(err2)
        # đợt 3 vượt trần (đã nhập 16/20, thêm 5 = 21) → chặn
        _, err3 = receive_purchase_lines(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 5, "action": "restock_new"}], actor="lan")
        self.assertIn("vượt số trên phiếu", err3)
        # chốt khi còn thiếu 4 → CHẶN (nhập đủ mới chốt được)
        _, err_thieu = confirm_purchase_receipt(self.conn, self.pu["id"], actor="lan")
        self.assertIn("Chưa nhập đủ", err_thieu)
        self.assertIn("thiếu 4", err_thieu)
        # nhập nốt 4 → chốt được: snapshot đủ cả 3 đợt
        _, err_du = receive_purchase_lines(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 4, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err_du)
        extra4, err4 = confirm_purchase_receipt(self.conn, self.pu["id"], actor="lan")
        self.assertIsNone(err4)
        self.assertEqual(len(extra4["result"]["restocked_new"]), 3)
        self.assertEqual(len(extra4["result"]["restocked_existing"]), 1)
        self.assertEqual(extra4["missing"], [])
        got = purchase_store.get_purchase(self.conn, self.pu["id"])
        self.assertIsNotNone(got["goods_handled_at"])
        # chốt lần 2 / nhập thêm sau chốt → chặn
        _, err5 = confirm_purchase_receipt(self.conn, self.pu["id"], actor="lan")
        self.assertEqual(err5, "already")
        _, err6 = receive_purchase_lines(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 1, "action": "restock_new"}], actor="lan")
        self.assertIn("đã chốt", err6)

    def test_unreceive_removes_existing_line(self):
        from server_app.purchase_goods import receive_purchase_lines, unreceive_purchase_line
        _, err = receive_purchase_lines(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 8, "action": "restock_existing", "box_id": self.box["id"]}],
            actor="lan")
        self.assertIsNone(err)
        self.assertEqual(self._rem(self.box["id"]), 108)
        aid = self.conn.execute(
            "SELECT id FROM box_allocations WHERE box_id = ? AND kind = 'purchase_in'",
            (self.box["id"],)).fetchone()[0]
        info, err2 = unreceive_purchase_line(self.conn, self.pu["id"], aid)
        self.assertIsNone(err2)
        self.assertEqual(info["box_id"], self.box["id"])
        self.assertEqual(self._rem(self.box["id"]), 100)         # về như cũ

    def test_unreceive_blocked_when_consumed(self):
        from inventory_store.allocations import allocate_picks
        from server_app.purchase_goods import receive_purchase_lines, unreceive_purchase_line
        _, err = receive_purchase_lines(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 8, "action": "restock_existing", "box_id": self.box["id"]}],
            actor="lan")
        self.assertIsNone(err)
        allocate_picks(self.conn, [{"box_id": self.box["id"], "quantity": 105}], 555)  # tiêu lẹm phần cộng
        aid = self.conn.execute(
            "SELECT id FROM box_allocations WHERE box_id = ? AND kind = 'purchase_in'",
            (self.box["id"],)).fetchone()[0]
        info, err2 = unreceive_purchase_line(self.conn, self.pu["id"], aid)
        self.assertIsNone(info)
        self.assertIn("đã dùng", err2)
        self.assertEqual(self._rem(self.box["id"]), 3)           # không gỡ gì

    def test_update_items_blocked_below_received_existing_line(self):
        # Guard sửa phiếu phải tính CẢ phần cộng vào thùng có sẵn đang nhập dở.
        from server_app.purchase_goods import receive_purchase_lines
        _, err = receive_purchase_lines(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 15, "action": "restock_existing", "box_id": self.box["id"]}],
            actor="lan")
        self.assertIsNone(err)
        ok, upd_err = purchase_store.update_purchase_items(
            self.conn, self.pu["id"], [{"sp": "KEO1", "sl": 10, "price": 5000}], 50000, "")
        self.assertFalse(ok)
        self.assertIn("đang giữ", upd_err)

    def test_delete_slip_blocked_while_receiving_in_progress(self):
        from server_app.purchase_goods import receive_purchase_lines
        _, err = receive_purchase_lines(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 5, "action": "restock_existing", "box_id": self.box["id"]}],
            actor="lan")
        self.assertIsNone(err)
        ok, del_err = purchase_store.soft_delete_purchase(self.conn, self.pu["id"], by="duy")
        self.assertFalse(ok)
        self.assertIn("cộng vào thùng", del_err)

    def test_delete_slip_blocked_while_boxes_from_slip_exist(self):
        # Sau hủy chốt thùng mới được GIỮ LẠI — xoá phiếu lúc này sẽ mồ côi thùng.
        from server_app.purchase_goods import undo_purchase_receipt
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 20, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err)
        new_id = extra["result"]["restocked_new"][0]["box_id"]
        _, undo_err = undo_purchase_receipt(self.conn, self.pu["id"])
        self.assertIsNone(undo_err)
        ok, del_err = purchase_store.soft_delete_purchase(self.conn, self.pu["id"], by="duy")
        self.assertFalse(ok)
        self.assertIn("thùng", del_err)
        self.assertIsNone(purchase_store.get_purchase(self.conn, self.pu["id"])["deleted_at"])
        from inventory_store.queries import delete_box
        delete_box(self.conn, new_id)
        ok2, _ = purchase_store.soft_delete_purchase(self.conn, self.pu["id"], by="duy")
        self.assertTrue(ok2)
        self.assertIsNotNone(purchase_store.get_purchase(self.conn, self.pu["id"])["deleted_at"])

    def test_update_items_blocked_when_goods_handled(self):
        # Re-check trong transaction — chốt kho đồng thời không bị sửa items đè lên.
        _, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 20, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err)
        ok, upd_err = purchase_store.update_purchase_items(
            self.conn, self.pu["id"], [{"sp": "KEO1", "sl": 25, "price": 5000}], 125000, "")
        self.assertFalse(ok)
        self.assertIn("đã nhập kho", upd_err)

    def test_update_items_blocked_below_retained_boxes(self):
        from server_app.purchase_goods import undo_purchase_receipt
        _, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 20, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err)
        _, undo_err = undo_purchase_receipt(self.conn, self.pu["id"])
        self.assertIsNone(undo_err)
        ok, upd_err = purchase_store.update_purchase_items(
            self.conn, self.pu["id"], [{"sp": "KEO1", "sl": 10, "price": 5000}], 50000, "")
        self.assertFalse(ok)
        self.assertIn("đang giữ", upd_err)
        ok2, upd_err2 = purchase_store.update_purchase_items(
            self.conn, self.pu["id"], [{"sp": "KEO1", "sl": 20, "price": 5000}], 100000, "")
        self.assertTrue(ok2, upd_err2)

    def test_undo_blocked_when_new_box_used(self):
        from inventory_store.allocations import allocate_picks
        from server_app.purchase_goods import undo_purchase_receipt
        new_id = self._receive_both()
        allocate_picks(self.conn, [{"box_id": new_id, "quantity": 3}], 555)   # đã xuất cho đơn
        info, err = undo_purchase_receipt(self.conn, self.pu["id"])
        self.assertIsNotNone(err)
        self.assertIn("phát sinh", err)
        self.assertIsNotNone(get_box(self.conn, new_id))                       # KHÔNG xoá gì (all-or-nothing)
        self.assertEqual(self._rem(self.box["id"]), 110)
        self.assertIsNotNone(purchase_store.get_purchase(self.conn, self.pu["id"])["goods_handled_at"])

    def test_undo_blocked_when_new_box_receives_other_purchase(self):
        from server_app.purchase_goods import undo_purchase_receipt
        extra, err = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 20, "action": "restock_new"}], actor="lan")
        self.assertIsNone(err)
        new_id = extra["result"]["restocked_new"][0]["box_id"]
        pu2 = purchase_store.add_purchase(
            self.conn, 1, [{"sp": "KEO1", "sl": 5, "price": 5000}], 25000, by="duy")
        _, err2 = apply_purchase_receipt(
            self.conn, pu2["id"],
            [{"sp": "KEO1", "quantity": 5, "action": "restock_existing", "box_id": new_id}],
            actor="lan")
        self.assertIsNone(err2)

        info, undo_err = undo_purchase_receipt(self.conn, self.pu["id"])
        self.assertIsNone(info)
        self.assertIn("phát sinh", undo_err)
        self.assertIsNotNone(get_box(self.conn, new_id))
        self.assertIsNotNone(purchase_store.get_purchase(self.conn, self.pu["id"])["goods_handled_at"])
        self.assertIsNotNone(purchase_store.get_purchase(self.conn, pu2["id"])["goods_handled_at"])

    def test_undo_blocked_when_received_stock_consumed(self):
        from inventory_store.allocations import allocate_picks
        from server_app.purchase_goods import undo_purchase_receipt
        apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 20, "action": "restock_existing", "box_id": self.box["id"]}],
            actor="lan")
        # tiêu 110/120 → remaining 10 < 20 đã cộng ⇒ phần hàng nhập đã bị dùng
        allocate_picks(self.conn, [{"box_id": self.box["id"], "quantity": 110}], 556)
        info, err = undo_purchase_receipt(self.conn, self.pu["id"])
        self.assertIsNotNone(err)
        self.assertIn("đã dùng một phần", err)

    def test_undo_requires_handled(self):
        from server_app.purchase_goods import undo_purchase_receipt
        _, err = undo_purchase_receipt(self.conn, self.pu["id"])
        self.assertIn("chưa chốt", err)

    def test_not_found_and_deleted(self):
        _, err = apply_purchase_receipt(self.conn, 999, [], actor="lan")
        self.assertEqual(err, "not_found")
        purchase_store.soft_delete_purchase(self.conn, self.pu["id"], by="admin")
        _, err2 = apply_purchase_receipt(self.conn, self.pu["id"], [], actor="lan")
        self.assertEqual(err2, "not_found")

    def test_receive_returns_audit_snapshots_for_box_events(self):
        # extra['audit'] = snapshot cho route ghi event kho (box.created / box.purchase_in)
        from server_app.purchase_goods import receive_purchase_lines, unreceive_purchase_line, undo_purchase_receipt
        extra, err = receive_purchase_lines(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 12, "action": "restock_new"},
             {"sp": "KEO1", "quantity": 8, "action": "restock_existing", "box_id": self.box["id"]}],
            actor="lan")
        self.assertIsNone(err)
        audit = extra["audit"]
        self.assertEqual(len(audit["created"]), 1)
        self.assertEqual(audit["created"][0]["remaining"], 12)
        self.assertEqual(len(audit["purchase_in"]), 1)
        pin = audit["purchase_in"][0]
        self.assertEqual(pin["box_id"], self.box["id"])
        self.assertEqual(pin["taken"], 8)
        self.assertEqual(pin["remaining"], 108)   # tồn SAU khi cộng
        # gỡ dòng cộng → audit purchase_in_removed với tồn sau khi gỡ
        aid = self.conn.execute(
            "SELECT id FROM box_allocations WHERE box_id = ? AND kind = 'purchase_in'",
            (self.box["id"],)).fetchone()["id"]
        info, err2 = unreceive_purchase_line(self.conn, self.pu["id"], aid)
        self.assertIsNone(err2)
        rem = info["audit"]["purchase_in_removed"][0]
        self.assertEqual(rem["taken"], 8)
        self.assertEqual(rem["remaining"], 100)
        # nhập đủ + chốt rồi hủy chốt → audit purchase_in_removed cho phần gỡ
        extra3, err3 = apply_purchase_receipt(
            self.conn, self.pu["id"],
            [{"sp": "KEO1", "quantity": 8, "action": "restock_existing", "box_id": self.box["id"]}],
            actor="lan")
        self.assertIsNone(err3)
        info4, err4 = undo_purchase_receipt(self.conn, self.pu["id"])
        self.assertIsNone(err4)
        undone = info4["audit"]["purchase_in_removed"]
        self.assertEqual(len(undone), 1)
        self.assertEqual(undone[0]["taken"], 8)
        self.assertEqual(undone[0]["remaining"], 100)


if __name__ == "__main__":
    unittest.main()
