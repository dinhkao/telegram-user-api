"""Guard NaN/Infinity cho các đường ghi box_allocations (allocate_picks /
transfer_between_boxes / receive_*_stock / create_adjustment) — NaN qua được mọi
so sánh `<= 0` (đều False) và `min(nan, cap)` không kẹp → 1 request đầu độc
remaining vĩnh viễn. + guard delete_allocation (kind/thread khớp, cấm xoá lẻ vế
transfer) + kẹp hoàn-NL-khi-xoá-thùng theo phần thực tiêu (_release_box_materials).
"""
from __future__ import annotations

import math
import os
import tempfile
import unittest

from inventory_store.adjustments import create_adjustment
from inventory_store.allocations import (allocate_picks, create_allocations_table,
                                         delete_allocation, get_allocation,
                                         receive_purchase_stock, receive_return_stock,
                                         transfer_between_boxes)
from inventory_store.queries import add_boxes, get_box
from inventory_store.schema import create_inventory_table, migrate_inventory_table
from product_store import create_products_table, migrate_products_table, upsert_product
from product_store.schema import _invalidate_products_cache
from utils.db import get_connection

_BADS = (float("nan"), "NaN", float("inf"), "-Infinity")


class _Base(unittest.TestCase):
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

    def _rem(self, box_id):
        q = float(get_box(self.conn, box_id)["quantity"])
        used = self.conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM box_allocations WHERE box_id = ?",
            (box_id,)).fetchone()[0]
        return q - float(used or 0)

    def _all_rows_finite(self):
        for r in self.conn.execute("SELECT quantity FROM box_allocations").fetchall():
            self.assertTrue(math.isfinite(float(r[0])), f"allocation NaN/Inf lọt vào DB: {r[0]}")


class NanGuardTest(_Base):
    def test_allocate_picks_rejects_nan_and_inf(self):
        for bad in _BADS:
            out = allocate_picks(self.conn, [{"box_id": self.box["id"], "quantity": bad}], 777)
            self.assertEqual(out, [], f"quantity={bad!r} phải bị bỏ qua")
        self.assertEqual(self._rem(self.box["id"]), 100)   # remaining nguyên vẹn
        self._all_rows_finite()

    def test_allocate_picks_none_takes_all_capped(self):
        # None = lấy hết phần còn lại (hành vi tài liệu hoá) — vẫn kẹp theo remaining
        out = allocate_picks(self.conn, [{"box_id": self.box["id"], "quantity": None}], 777)
        self.assertEqual(out[0]["quantity"], 100)
        self.assertEqual(self._rem(self.box["id"]), 0)
        self._all_rows_finite()

    def test_transfer_rejects_nan_and_inf(self):
        other = add_boxes(self.conn, "KEO1", [50])[0]
        for bad in _BADS:
            res, err = transfer_between_boxes(self.conn, self.box["id"], other["id"], bad)
            self.assertIsNone(res)
            self.assertIn("không hợp lệ", err)
        self.assertEqual(self._rem(self.box["id"]), 100)
        self.assertEqual(self._rem(other["id"]), 50)
        self._all_rows_finite()

    def test_create_adjustment_rejects_nan_and_inf(self):
        for bad in _BADS:
            adj, err = create_adjustment(self.conn, self.box["id"], new_remaining=bad,
                                         reason="test", by="duy")
            self.assertIsNone(adj)
            self.assertIn("không hợp lệ", err)
        self.assertEqual(self._rem(self.box["id"]), 100)
        self._all_rows_finite()

    def test_receive_stock_rejects_nan_and_inf(self):
        for bad in _BADS:
            self.assertFalse(receive_return_stock(self.conn, self.box["id"], bad, 1))
            self.assertFalse(receive_purchase_stock(self.conn, self.box["id"], bad, 1))
        self.assertEqual(self._rem(self.box["id"]), 100)
        self._all_rows_finite()


class DeleteAllocationGuardTest(_Base):
    def test_kind_and_thread_must_match(self):
        aid = allocate_picks(self.conn, [{"box_id": self.box["id"], "quantity": 10}],
                             777)[0]["allocation_id"]
        # sai thread → từ chối, dòng còn nguyên
        self.assertFalse(delete_allocation(self.conn, aid, order_thread_id=888))
        self.assertIsNotNone(get_allocation(self.conn, aid))
        # sai kind → từ chối
        self.assertFalse(delete_allocation(self.conn, aid, kind="production"))
        self.assertIsNotNone(get_allocation(self.conn, aid))
        # đúng kind + thread → xoá
        self.assertTrue(delete_allocation(self.conn, aid, kind="order", order_thread_id=777))
        self.assertIsNone(get_allocation(self.conn, aid))
        # id không tồn tại → False, không nổ
        self.assertFalse(delete_allocation(self.conn, aid))

    def test_transfer_legs_refused_outright(self):
        other = add_boxes(self.conn, "KEO1", [50])[0]
        res, err = transfer_between_boxes(self.conn, self.box["id"], other["id"], 20)
        self.assertIsNone(err)
        rows = self.conn.execute(
            "SELECT id, kind, order_thread_id FROM box_allocations "
            "WHERE kind IN ('transfer_in','transfer_out')").fetchall()
        self.assertEqual(len(rows), 2)
        for r in rows:
            # kể cả khai đúng kind + thread — xoá 1 vế phá bút toán kép → raise
            with self.assertRaises(ValueError):
                delete_allocation(self.conn, r["id"], kind=r["kind"],
                                  order_thread_id=r["order_thread_id"])
        # cả 2 vế còn nguyên, tổng tồn bảo toàn
        self.assertEqual(self._rem(self.box["id"]) + self._rem(other["id"]), 150)


class BoxDeleteRefundCapTest(unittest.TestCase):
    """Xoá thùng thành phẩm hoàn NL theo phần THỰC TIÊU của phiếu — công thức bị
    sửa SAU khi SX không được in tồn từ hư không (fix kẹp share theo tiêu thật)."""

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
        from recipe_store import create_recipe_table
        create_recipe_table(self.conn)
        # bảng phiếu SX (get_slip cần)
        from production_store.schema import create_production_table, migrate_production_table
        create_production_table(self.conn)
        migrate_production_table(self.conn)

    def tearDown(self):
        self.conn.close()
        _invalidate_products_cache()
        os.unlink(self.path)

    def _rem_total(self, code):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(b.quantity - COALESCE((SELECT SUM(x.quantity) "
            "FROM box_allocations x WHERE x.box_id=b.id),0)),0) FROM inventory_boxes b "
            "JOIN products p ON p.id = b.product_id WHERE p.code = ? "
            "AND COALESCE(b.disabled,0)=0", (code,)).fetchone()
        return float(row[0] or 0)

    def test_recipe_edited_up_refund_capped_to_actual_consumption(self):
        from inventory_store.allocations import fifo_consume
        from inventory_store.queries import delete_box
        from production_store import upsert_slip
        from recipe_store import set_recipe_line
        from server_app.inventory_routes import _release_box_materials
        c = self.conn
        upsert_product(c, "SP", "Thành phẩm", unit="cây")
        upsert_product(c, "M", "Nguyên liệu", unit="cây")
        set_recipe_line(c, "SP", "M", 1.0)              # ratio 1.0 lúc SX
        mat = add_boxes(c, "M", [500])[0]
        slip_id = 9001
        upsert_slip(c, slip_id, sp_name="SP")
        # phiếu tiêu 200 M cho 2 thùng SP × 100 (ratio 1.0)
        fifo_consume(c, slip_id, [{"code": "M", "amount": 200}])
        b1, b2 = add_boxes(c, "SP", [100, 100], source_thread_id=slip_id)
        self.assertEqual(self._rem_total("M"), 300)

        set_recipe_line(c, "SP", "M", 2.0)              # sửa công thức SAU khi SX

        # Xoá thùng 1: công thức mới đòi 200 nhưng phần chia thực tiêu của thùng
        # = 200 × 100/(100+100) = 100 → hoàn ĐÚNG 100, không phải 200.
        restored = _release_box_materials(c, get_box(c, b1["id"]))
        delete_box(c, b1["id"])
        self.assertEqual(sum(r["amount"] for r in restored), 100)
        self.assertEqual(self._rem_total("M"), 400)

        # Xoá thùng 2: nhận trọn phần còn tiêu (100) — tổng hoàn đủ đúng 200 đã tiêu.
        restored2 = _release_box_materials(c, get_box(c, b2["id"]))
        delete_box(c, b2["id"])
        self.assertEqual(sum(r["amount"] for r in restored2), 100)
        self.assertEqual(self._rem_total("M"), 500)     # về đúng ban đầu, không dư

    def test_recipe_unchanged_refund_exact(self):
        from inventory_store.allocations import fifo_consume
        from inventory_store.queries import delete_box
        from production_store import upsert_slip
        from recipe_store import set_recipe_line
        from server_app.inventory_routes import _release_box_materials
        c = self.conn
        upsert_product(c, "SP", "Thành phẩm", unit="cây")
        upsert_product(c, "M", "Nguyên liệu", unit="cây")
        set_recipe_line(c, "SP", "M", 1.5)
        add_boxes(c, "M", [500])
        slip_id = 9002
        upsert_slip(c, slip_id, sp_name="SP")
        fifo_consume(c, slip_id, [{"code": "M", "amount": 300}])   # 2×100 SP × 1.5
        b1, b2 = add_boxes(c, "SP", [100, 100], source_thread_id=slip_id)
        for b, expect_total in ((b1, 350), (b2, 500)):
            restored = _release_box_materials(c, get_box(c, b["id"]))
            delete_box(c, b["id"])
            self.assertEqual(sum(r["amount"] for r in restored), 150)
            self.assertEqual(self._rem_total("M"), expect_total)


class ReturnMaterialNoConsumeTest(BoxDeleteRefundCapTest):
    """Rã thùng nguyên kiện (return-material): phiếu nguồn KHÔNG tiêu NL (đóng gói
    qua toggle admin bỏ NL) → KHÔNG được tạo thùng NL 'ratio × số' từ hư không."""

    def _seed(self, consume: float):
        from inventory_store.allocations import fifo_consume
        from production_store import upsert_slip
        from recipe_store import set_recipe_line
        c = self.conn
        upsert_product(c, "KIEN", "Thùng nguyên kiện", unit="thùng")
        # self_container DERIVE từ vai 📦 (bulk_unit_id is not None; 0 = đơn vị gốc)
        upsert_product(c, "KIEN", bulk_unit_id=0)
        upsert_product(c, "M", "Nguyên liệu", unit="cây")
        set_recipe_line(c, "KIEN", "M", 2.0)
        add_boxes(c, "M", [500])
        slip_id = 9100
        upsert_slip(c, slip_id, sp_name="KIEN")
        if consume > 0:
            fifo_consume(c, slip_id, [{"code": "M", "amount": consume}])
        return add_boxes(c, "KIEN", [30], source_thread_id=slip_id)[0]

    def test_no_consumption_returns_400_and_creates_nothing(self):
        from server_app.inventory_routes import _return_material_core
        box = self._seed(consume=0)
        before = self._rem_total("M")
        status, res = _return_material_core(self.conn, box["id"], "admin")
        self.assertEqual(status, "noconsume")
        self.assertIsNone(res)
        self.assertEqual(self._rem_total("M"), before)                 # không in NL từ hư không
        self.assertFalse(get_box(self.conn, box["id"])["disabled"])    # thùng còn nguyên, không vô hiệu

    def test_partial_consumption_returns_only_consumed_plus_topup(self):
        # Phiếu CÓ tiêu (60 = 30 × 2.0) → rã hoàn đủ 60 (đảo tiêu hao, thiếu mới bù).
        from server_app.inventory_routes import _return_material_core
        box = self._seed(consume=60)
        before = self._rem_total("M")                                  # 440
        status, (src, restored) = _return_material_core(self.conn, box["id"], "admin")
        self.assertEqual(status, "ok")
        self.assertEqual(sum(r["amount"] for r in restored), 60)
        self.assertEqual(self._rem_total("M"), before + 60)
        self.assertTrue(get_box(self.conn, box["id"])["disabled"])     # thùng vô hiệu, giữ lịch sử


if __name__ == "__main__":
    unittest.main()
