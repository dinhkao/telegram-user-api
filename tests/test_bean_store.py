"""Test bean_store (KHO ĐẬU): CRUD danh mục đậu + kho, phiếu nhập/xuất/điều chỉnh,
tồn = Σ delta phiếu còn sống, guard tồn âm (lúc tạo lẫn lúc xoá), và logic thuần
domain (parse_qty kiểu Việt, delta_for, build_stock_table)."""
from __future__ import annotations

import os
import tempfile
import unittest

import bean_store
from bean_store import domain
from utils.db import get_connection


class BeanStoreTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        bean_store.ensure_tables(self.conn)
        self.kho_a, _ = bean_store.add_place(self.conn, "Kho A", by="duy")
        self.kho_b, _ = bean_store.add_place(self.conn, "Kho B", by="duy")
        self.xanh, _ = bean_store.add_bean(self.conn, "Đậu xanh", by="duy")
        self.phong, _ = bean_store.add_bean(self.conn, "Đậu phộng", unit="bao", by="duy")

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def _nhap(self, bean, place, qty, **kw):
        return bean_store.create_slip(
            self.conn, "nhap", place["id"], [{"bean_id": bean["id"], "quantity": qty}],
            by="duy", **kw)

    # ── Danh mục ─────────────────────────────────────────────────────────────
    def test_bean_needs_name_and_unique(self):
        b, err = bean_store.add_bean(self.conn, "   ")
        self.assertIsNone(b)
        self.assertIn("tên", err.lower())
        _, err = bean_store.add_bean(self.conn, "đậu xanh")   # trùng, khác hoa/thường
        self.assertIsNotNone(err)

    def test_place_crud_and_default_unit(self):
        self.assertEqual(self.xanh["unit"], "kg")
        self.assertEqual(self.phong["unit"], "bao")
        upd, err = bean_store.update_place(self.conn, self.kho_b["id"], name="Kho B1", note="sau nhà")
        self.assertIsNone(err)
        self.assertEqual(upd["name"], "Kho B1")
        self.assertEqual(upd["note"], "sau nhà")
        names = [p["name"] for p in bean_store.list_places(self.conn)]
        self.assertEqual(names, ["Kho A", "Kho B1"])

    def test_delete_blocked_while_slips_exist(self):
        self._nhap(self.xanh, self.kho_a, 100)
        ok, err = bean_store.soft_delete_bean(self.conn, self.xanh["id"], by="duy")
        self.assertFalse(ok)
        self.assertIn("phiếu", err.lower())
        ok, err = bean_store.soft_delete_place(self.conn, self.kho_a["id"], by="duy")
        self.assertFalse(ok)
        self.assertIn("phiếu", err.lower())
        # loại đậu chưa dùng thì xoá được
        ok, err = bean_store.soft_delete_bean(self.conn, self.phong["id"], by="duy")
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertIsNone(bean_store.get_bean(self.conn, self.phong["id"]))

    # ── Phiếu + tồn ──────────────────────────────────────────────────────────
    def test_nhap_xuat_stock(self):
        slip, err = self._nhap(self.xanh, self.kho_a, 100)
        self.assertIsNone(err)
        self.assertEqual(slip["kind"], "nhap")
        self.assertEqual(slip["items"][0]["delta"], 100)
        self.assertEqual(slip["place_name"], "Kho A")
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho_a["id"]), 100)

        out, err = bean_store.create_slip(
            self.conn, "xuat", self.kho_a["id"],
            [{"bean_id": self.xanh["id"], "quantity": "12,5"}], by="duy")
        self.assertIsNone(err)
        self.assertEqual(out["items"][0]["delta"], -12.5)
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho_a["id"]), 87.5)
        # kho khác KHÔNG bị ảnh hưởng
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho_b["id"]), 0)

    def test_xuat_qua_ton_bi_chan(self):
        self._nhap(self.xanh, self.kho_a, 10)
        slip, err = bean_store.create_slip(
            self.conn, "xuat", self.kho_a["id"],
            [{"bean_id": self.xanh["id"], "quantity": 11}], by="duy")
        self.assertIsNone(slip)
        self.assertIn("không đủ", err.lower())
        # tồn giữ nguyên, không có phiếu rác
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho_a["id"]), 10)
        self.assertEqual(bean_store.list_slips(self.conn)[1], 1)

    def test_dieu_chinh_dat_ton_ve_so_dem(self):
        self._nhap(self.xanh, self.kho_a, 100)
        slip, err = bean_store.create_slip(
            self.conn, "dieu_chinh", self.kho_a["id"],
            [{"bean_id": self.xanh["id"], "quantity": 92, "note": "hao hụt"}],
            note="kiểm kho tháng 8", by="duy")
        self.assertIsNone(err)
        item = slip["items"][0]
        self.assertEqual(item["before_qty"], 100)
        self.assertEqual(item["delta"], -8)
        self.assertEqual(item["quantity"], 92)   # số ĐẾM, không phải chênh lệch
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho_a["id"]), 92)
        # điều chỉnh về 0 hợp lệ; về số âm thì không có (số âm bị chặn từ đầu)
        _, err = bean_store.create_slip(
            self.conn, "dieu_chinh", self.kho_a["id"],
            [{"bean_id": self.xanh["id"], "quantity": 0}], by="duy")
        self.assertIsNone(err)
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho_a["id"]), 0)

    def test_items_validate(self):
        _, err = bean_store.create_slip(self.conn, "nhap", self.kho_a["id"], [], by="duy")
        self.assertIn("ít nhất 1 dòng", err)
        _, err = bean_store.create_slip(self.conn, "lung_tung", self.kho_a["id"],
                                        [{"bean_id": self.xanh["id"], "quantity": 1}], by="duy")
        self.assertIn("Loại phiếu", err)
        _, err = bean_store.create_slip(self.conn, "nhap", 999,
                                        [{"bean_id": self.xanh["id"], "quantity": 1}], by="duy")
        self.assertIn("Kho", err)
        _, err = bean_store.create_slip(self.conn, "nhap", self.kho_a["id"],
                                        [{"bean_id": self.xanh["id"], "quantity": 1},
                                         {"bean_id": self.xanh["id"], "quantity": 2}], by="duy")
        self.assertIn("2 dòng", err)
        _, err = bean_store.create_slip(self.conn, "nhap", self.kho_a["id"],
                                        [{"bean_id": self.xanh["id"], "quantity": 0}], by="duy")
        self.assertIn("lớn hơn 0", err)
        _, err = bean_store.create_slip(self.conn, "nhap", self.kho_a["id"],
                                        [{"bean_id": self.xanh["id"], "quantity": "abc"}], by="duy")
        self.assertIn("không hợp lệ", err)

    def test_delete_slip_restores_stock(self):
        slip, _ = self._nhap(self.xanh, self.kho_a, 50)
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho_a["id"]), 50)
        gone, err = bean_store.soft_delete_slip(self.conn, slip["id"], by="duy")
        self.assertIsNone(err)
        self.assertEqual(gone["id"], slip["id"])
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho_a["id"]), 0)
        self.assertIsNone(bean_store.get_slip(self.conn, slip["id"]))
        _, err = bean_store.soft_delete_slip(self.conn, slip["id"], by="duy")
        self.assertIn("Không tìm thấy", err)

    def test_delete_slip_blocked_when_would_go_negative(self):
        nhap, _ = self._nhap(self.xanh, self.kho_a, 30)
        bean_store.create_slip(self.conn, "xuat", self.kho_a["id"],
                               [{"bean_id": self.xanh["id"], "quantity": 25}], by="duy")
        _, err = bean_store.soft_delete_slip(self.conn, nhap["id"], by="duy")
        self.assertIn("âm kho", err)
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho_a["id"]), 5)

    def test_list_slips_filters(self):
        self._nhap(self.xanh, self.kho_a, 10)
        self._nhap(self.phong, self.kho_b, 4)
        bean_store.create_slip(self.conn, "xuat", self.kho_a["id"],
                               [{"bean_id": self.xanh["id"], "quantity": 3}], by="duy")
        self.assertEqual(bean_store.list_slips(self.conn)[1], 3)
        self.assertEqual(bean_store.list_slips(self.conn, kind="xuat")[1], 1)
        self.assertEqual(bean_store.list_slips(self.conn, place_id=self.kho_b["id"])[1], 1)
        self.assertEqual(bean_store.list_slips(self.conn, bean_id=self.xanh["id"])[1], 2)
        rows, _ = bean_store.list_slips(self.conn, limit=2)
        self.assertEqual(len(rows), 2)

    def test_stock_cells_and_table(self):
        self._nhap(self.xanh, self.kho_a, 100)
        self._nhap(self.xanh, self.kho_b, 20)
        self._nhap(self.phong, self.kho_b, 5)
        cells = bean_store.stock_cells(self.conn)
        self.assertEqual(len(cells), 3)
        table = domain.build_stock_table(bean_store.list_beans(self.conn),
                                         bean_store.list_places(self.conn), cells)
        by_bean = {b["name"]: b for b in table["by_bean"]}
        self.assertEqual(by_bean["Đậu xanh"]["total"], 120)
        self.assertEqual(len(by_bean["Đậu xanh"]["places"]), 2)
        self.assertEqual(by_bean["Đậu phộng"]["unit"], "bao")
        by_place = {p["name"]: p for p in table["by_place"]}
        self.assertEqual(by_place["Kho B"]["total"], 25)
        self.assertEqual(table["total"], 125)
        self.assertEqual(bean_store.stock_by_bean(self.conn)[self.xanh["id"]], 120)


class BeanUnitTest(unittest.TestCase):
    """QUY ĐỔI ĐƠN VỊ: mọi số trong DB theo đơn vị GỐC, snapshot giữ cách người gõ."""

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        bean_store.ensure_tables(self.conn)
        self.kho, _ = bean_store.add_place(self.conn, "Kho A", by="duy")
        self.xanh, _ = bean_store.add_bean(self.conn, "Đậu xanh", unit="kg", by="duy")
        self.bao, _ = bean_store.add_unit(self.conn, self.xanh["id"], "bao", 50, "kg", by="duy")

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def test_add_validate(self):
        _, err = bean_store.add_unit(self.conn, self.xanh["id"], "  ", 10, "kg")
        self.assertIn("tên", err.lower())
        _, err = bean_store.add_unit(self.conn, self.xanh["id"], "tạ", 0, "kg")
        self.assertIn("lớn hơn 0", err)
        _, err = bean_store.add_unit(self.conn, self.xanh["id"], "tạ", "abc", "kg")
        self.assertIn("không hợp lệ", err)
        _, err = bean_store.add_unit(self.conn, self.xanh["id"], "kg", 2, "kg")
        self.assertIn("đơn vị gốc", err)
        # trùng tên (bỏ dấu, không phân biệt hoa thường)
        _, err = bean_store.add_unit(self.conn, self.xanh["id"], "BAO", 25, "kg")
        self.assertIn("đã có", err)
        # tỉ lệ gõ kiểu Việt
        u, err = bean_store.add_unit(self.conn, self.xanh["id"], "lon", "0,5", "kg")
        self.assertIsNone(err)
        self.assertEqual(u["factor"], 0.5)

    def test_units_list_and_update_delete(self):
        units = bean_store.list_units(self.conn, self.xanh["id"])
        self.assertEqual([u["name"] for u in units], ["bao"])
        upd, err = bean_store.update_unit(self.conn, self.bao["id"], name="bao lớn",
                                          factor=60, base_unit="kg")
        self.assertIsNone(err)
        self.assertEqual((upd["name"], upd["factor"]), ("bao lớn", 60))
        by_bean = bean_store.units_by_bean(self.conn)
        self.assertEqual(by_bean[self.xanh["id"]][0]["factor"], 60)
        gone, err = bean_store.delete_unit(self.conn, self.bao["id"])
        self.assertIsNone(err)
        self.assertEqual(gone["name"], "bao lớn")
        self.assertEqual(bean_store.list_units(self.conn, self.xanh["id"]), [])

    def test_resolve_unit(self):
        self.assertEqual(bean_store.resolve_unit(self.conn, self.xanh["id"], None), ("", 1.0, None))
        self.assertEqual(bean_store.resolve_unit(self.conn, self.xanh["id"], 0), ("", 1.0, None))
        self.assertEqual(bean_store.resolve_unit(self.conn, self.xanh["id"], self.bao["id"]),
                         ("bao", 50.0, None))
        other, _ = bean_store.add_bean(self.conn, "Đậu đỏ", by="duy")
        _, _, err = bean_store.resolve_unit(self.conn, other["id"], self.bao["id"])
        self.assertIn("không thuộc", err)

    def test_slip_converts_to_base_unit(self):
        slip, err = bean_store.create_slip(
            self.conn, "nhap", self.kho["id"],
            [{"bean_id": self.xanh["id"], "quantity": 2, "unit_id": self.bao["id"]}], by="duy")
        self.assertIsNone(err)
        it = slip["items"][0]
        self.assertEqual(it["quantity"], 100)      # 2 bao × 50 = 100 kg (đơn vị gốc)
        self.assertEqual(it["delta"], 100)
        self.assertEqual(it["entered_qty"], 2)     # snapshot: người dùng gõ "2 bao"
        self.assertEqual(it["entered_unit"], "bao")
        self.assertTrue(it["converted"])
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho["id"]), 100)

        # xuất bằng đơn vị gốc trên cùng tồn đó
        out, err = bean_store.create_slip(
            self.conn, "xuat", self.kho["id"],
            [{"bean_id": self.xanh["id"], "quantity": 30}], by="duy")
        self.assertIsNone(err)
        self.assertEqual(out["items"][0]["entered_unit"], "kg")   # rơi về đơn vị gốc
        self.assertFalse(out["items"][0]["converted"])
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho["id"]), 70)

    def test_xuat_theo_don_vi_phu_chan_theo_ton_goc(self):
        bean_store.create_slip(self.conn, "nhap", self.kho["id"],
                               [{"bean_id": self.xanh["id"], "quantity": 60}], by="duy")
        # 2 bao = 100 kg > 60 kg đang có → chặn, báo lỗi nói CẢ 2 đơn vị
        _, err = bean_store.create_slip(
            self.conn, "xuat", self.kho["id"],
            [{"bean_id": self.xanh["id"], "quantity": 2, "unit_id": self.bao["id"]}], by="duy")
        self.assertIn("không đủ", err.lower())
        self.assertIn("còn 60 kg", err)
        self.assertIn("100 kg (2 bao)", err)
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho["id"]), 60)

    def test_dieu_chinh_theo_don_vi_phu(self):
        bean_store.create_slip(self.conn, "nhap", self.kho["id"],
                               [{"bean_id": self.xanh["id"], "quantity": 120}], by="duy")
        slip, err = bean_store.create_slip(
            self.conn, "dieu_chinh", self.kho["id"],
            [{"bean_id": self.xanh["id"], "quantity": 2, "unit_id": self.bao["id"]}], by="duy")
        self.assertIsNone(err)
        it = slip["items"][0]
        self.assertEqual(it["quantity"], 100)   # đếm được 2 bao = 100 kg
        self.assertEqual(it["before_qty"], 120)
        self.assertEqual(it["delta"], -20)
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho["id"]), 100)

    def test_unit_id_la_cua_dau_khac_bi_chan(self):
        other, _ = bean_store.add_bean(self.conn, "Đậu đỏ", by="duy")
        _, err = bean_store.create_slip(
            self.conn, "nhap", self.kho["id"],
            [{"bean_id": other["id"], "quantity": 1, "unit_id": self.bao["id"]}], by="duy")
        self.assertIn("không thuộc", err)

    def test_doi_ti_le_khong_tinh_lai_phieu_cu(self):
        slip, _ = bean_store.create_slip(
            self.conn, "nhap", self.kho["id"],
            [{"bean_id": self.xanh["id"], "quantity": 2, "unit_id": self.bao["id"]}], by="duy")
        bean_store.update_unit(self.conn, self.bao["id"], factor=70, base_unit="kg")
        again = bean_store.get_slip(self.conn, slip["id"])
        self.assertEqual(again["items"][0]["quantity"], 100)     # vẫn 100 kg như lúc nhập
        self.assertEqual(again["items"][0]["unit_factor"], 50)   # snapshot hệ số cũ
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho["id"]), 100)

    # ── Đổi ĐƠN VỊ CHÍNH (kg → bao) ──────────────────────────────────────────
    def test_doi_don_vi_chinh_giu_nguyen_luong_hang(self):
        bean_store.create_slip(self.conn, "nhap", self.kho["id"],
                               [{"bean_id": self.xanh["id"], "quantity": 2,
                                 "unit_id": self.bao["id"]}], by="duy")   # 100 kg
        bean_store.create_slip(self.conn, "xuat", self.kho["id"],
                               [{"bean_id": self.xanh["id"], "quantity": 25}], by="duy")
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho["id"]), 75)

        res, err = bean_store.set_base_unit(self.conn, self.xanh["id"], self.bao["id"])
        self.assertIsNone(err)
        self.assertEqual((res["old_base"], res["new_base"]), ("kg", "bao"))
        # 75 kg = 1,5 bao — lượng hàng y nguyên, chỉ đổi thước đo
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho["id"]), 1.5)
        self.assertEqual(bean_store.get_bean(self.conn, self.xanh["id"])["unit"], "bao")
        # đơn vị gốc CŨ thành đơn vị quy đổi: 1 kg = 0,02 bao
        units = bean_store.list_units(self.conn, self.xanh["id"])
        self.assertEqual([(u["name"], u["factor"]) for u in units], [("kg", 0.02)])

    def test_doi_don_vi_chinh_dao_nguoc_duoc(self):
        bean_store.create_slip(self.conn, "nhap", self.kho["id"],
                               [{"bean_id": self.xanh["id"], "quantity": 130}], by="duy")
        bean_store.set_base_unit(self.conn, self.xanh["id"], self.bao["id"])
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho["id"]), 2.6)
        kg = bean_store.list_units(self.conn, self.xanh["id"])[0]
        bean_store.set_base_unit(self.conn, self.xanh["id"], kg["id"])
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho["id"]), 130)
        self.assertEqual(bean_store.get_bean(self.conn, self.xanh["id"])["unit"], "kg")
        self.assertEqual([(u["name"], u["factor"])
                          for u in bean_store.list_units(self.conn, self.xanh["id"])],
                         [("bao", 50.0)])

    def test_doi_don_vi_chinh_quy_doi_ca_don_vi_khac(self):
        bean_store.add_unit(self.conn, self.xanh["id"], "tạ", 100, "kg", by="duy")
        bean_store.set_base_unit(self.conn, self.xanh["id"], self.bao["id"])
        units = {u["name"]: u["factor"] for u in bean_store.list_units(self.conn, self.xanh["id"])}
        self.assertEqual(units["tạ"], 2)      # 1 tạ = 100 kg = 2 bao
        self.assertEqual(units["kg"], 0.02)

    def test_doi_don_vi_chinh_giu_snapshot_phieu_dung_thuoc_do_moi(self):
        slip, _ = bean_store.create_slip(
            self.conn, "nhap", self.kho["id"],
            [{"bean_id": self.xanh["id"], "quantity": 2, "unit_id": self.bao["id"]}], by="duy")
        bean_store.set_base_unit(self.conn, self.xanh["id"], self.bao["id"])
        it = bean_store.get_slip(self.conn, slip["id"])["items"][0]
        self.assertEqual(it["quantity"], 2)      # 100 kg = 2 bao
        self.assertEqual(it["entered_qty"], 2)   # người dùng vẫn đã gõ "2 bao"
        self.assertEqual(it["unit_factor"], 1)   # 1 bao = 1 bao (gốc mới)

    def test_doi_don_vi_chinh_loi(self):
        _, err = bean_store.set_base_unit(self.conn, self.xanh["id"], 9999)
        self.assertIn("không thuộc", err)
        other, _ = bean_store.add_bean(self.conn, "Đậu đỏ", by="duy")
        _, err = bean_store.set_base_unit(self.conn, other["id"], self.bao["id"])
        self.assertIn("không thuộc", err)

    def test_db_cu_thieu_cot_duoc_va_tai_cho(self):
        """DB tạo bởi bản TRƯỚC khi có quy đổi đơn vị (bean_moves thiếu 3 cột
        snapshot) — ensure_tables phải ALTER thêm, dòng cũ vẫn đọc được."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = get_connection(path)
        try:
            conn.execute("""CREATE TABLE bean_moves (
                id INTEGER PRIMARY KEY AUTOINCREMENT, slip_id INTEGER NOT NULL,
                bean_id INTEGER NOT NULL, place_id INTEGER NOT NULL, delta REAL NOT NULL,
                quantity REAL NOT NULL, before_qty REAL, note TEXT DEFAULT '')""")
            bean_store.ensure_tables(conn)
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(bean_moves)").fetchall()}
            self.assertTrue({"entered_qty", "unit_name", "unit_factor"} <= cols)

            place, _ = bean_store.add_place(conn, "Kho A", by="duy")
            bean, _ = bean_store.add_bean(conn, "Đậu xanh", by="duy")
            # dòng kiểu CŨ: không có snapshot đơn vị
            conn.execute("INSERT INTO bean_slips (kind, place_id, ymd, created_at) "
                         "VALUES ('nhap', ?, '2026-08-09', '2026-08-09T00:00:00+00:00')",
                         (place["id"],))
            conn.execute("INSERT INTO bean_moves (slip_id, bean_id, place_id, delta, quantity) "
                         "VALUES (1, ?, ?, 40, 40)", (bean["id"], place["id"]))
            slip = bean_store.get_slip(conn, 1)
            it = slip["items"][0]
            self.assertEqual(it["entered_qty"], 40)      # suy về chính số đã ghi
            self.assertEqual(it["entered_unit"], "kg")   # đơn vị gốc
            self.assertEqual(it["unit_factor"], 1)
            self.assertFalse(it["converted"])
            self.assertEqual(bean_store.stock_of(conn, bean["id"], place["id"]), 40)
        finally:
            conn.close()
            os.unlink(path)

    def test_xoa_don_vi_khong_lam_hong_phieu_cu(self):
        slip, _ = bean_store.create_slip(
            self.conn, "nhap", self.kho["id"],
            [{"bean_id": self.xanh["id"], "quantity": 3, "unit_id": self.bao["id"]}], by="duy")
        bean_store.delete_unit(self.conn, self.bao["id"])
        again = bean_store.get_slip(self.conn, slip["id"])
        self.assertEqual(again["items"][0]["quantity"], 150)
        self.assertEqual(again["items"][0]["entered_unit"], "bao")
        self.assertEqual(bean_store.stock_of(self.conn, self.xanh["id"], self.kho["id"]), 150)


class BeanDomainTest(unittest.TestCase):
    def test_parse_qty(self):
        self.assertEqual(domain.parse_qty("12,5"), 12.5)
        self.assertEqual(domain.parse_qty(" 3 "), 3)
        self.assertIsNone(domain.parse_qty("abc"))
        self.assertIsNone(domain.parse_qty(""))
        self.assertIsNone(domain.parse_qty(None))

    def test_fmt_qty(self):
        self.assertEqual(domain.fmt_qty(120.5), "120,5")
        self.assertEqual(domain.fmt_qty(12.0), "12")
        self.assertEqual(domain.fmt_qty(0), "0")

    def test_delta_for(self):
        self.assertEqual(domain.delta_for("nhap", 10, 0), 10)
        self.assertEqual(domain.delta_for("xuat", 10, 99), -10)
        self.assertEqual(domain.delta_for("dieu_chinh", 8, 10), -2)
        self.assertEqual(domain.delta_for("dieu_chinh", 12, 10), 2)
        with self.assertRaises(ValueError):
            domain.delta_for("gi_do", 1, 0)

    def test_build_stock_table_skips_zero_cells(self):
        beans = [{"id": 1, "name": "Đậu xanh", "unit": "kg"}]
        places = [{"id": 7, "name": "Kho A"}, {"id": 8, "name": "Kho B"}]
        table = domain.build_stock_table(beans, places, [{"bean_id": 1, "place_id": 7, "qty": 5}])
        self.assertEqual(table["by_bean"][0]["places"], [{"place_id": 7, "qty": 5.0}])
        self.assertEqual(table["by_place"][1]["beans"], [])    # Kho B rỗng vẫn có mặt
        self.assertEqual(table["by_place"][1]["total"], 0)
        self.assertEqual(table["total"], 5)


if __name__ == "__main__":
    unittest.main()
