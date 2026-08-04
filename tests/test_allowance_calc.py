"""Test PHỤ CẤP TÍNH THEO CÔNG THỨC (salary_store/allowance_calc.py + store).

Luật chốt 2026-08-04: khoản nhập theo % lương gốc hoặc theo đơn giá × ngày công phải
TỰ CHẠY THEO lương gốc — sửa báo cáo SX / sửa chấm công thì số phụ cấp đổi theo, KHÔNG
đứng yên như số chốt. Khoản nhập tiền thẳng thì vẫn bất biến như cũ.
"""
from __future__ import annotations

import os
import tempfile
import unittest

import attendance_store
import salary_store
from salary_store.allowance_calc import allowance_amount, calc_label, normalize
from utils.db import get_connection
from worker_store import add_worker, ensure_table, update_worker


class AllowanceCalcPureTest(unittest.TestCase):
    def test_tien_co_dinh_khong_phu_thuoc_goc(self):
        self.assertEqual(allowance_amount(None, None, 300_000, base=9_000_000, cong=24), 300_000)
        self.assertEqual(allowance_amount("", 0, 300_000, base=0, cong=0), 300_000)

    def test_phan_tram_theo_luong_goc(self):
        self.assertEqual(allowance_amount("pct", 10, 0, base=9_042_610, cong=24), 904_261)
        self.assertEqual(allowance_amount("pct", 12.5, 0, base=8_000_000, cong=24), 1_000_000)

    def test_don_gia_nhan_ngay_cong(self):
        self.assertEqual(allowance_amount("day", 20_000, 0, base=0, cong=24.5), 490_000)

    def test_goc_bang_0_thi_ra_0(self):
        self.assertEqual(allowance_amount("pct", 10, 999, base=0, cong=24), 0)
        self.assertEqual(allowance_amount("day", 20_000, 999, base=9_000_000, cong=0), 0)

    def test_goc_am_coi_nhu_0(self):
        self.assertEqual(allowance_amount("pct", 10, 0, base=-5_000, cong=-3), 0)

    def test_normalize_loai_bo_so_vo_ly(self):
        self.assertEqual(normalize("pct", 10), ("pct", 10.0))
        self.assertEqual(normalize("day", "20000"), ("day", 20000.0))
        self.assertEqual(normalize("pct", 150), (None, None))    # >100% chắc gõ nhầm
        self.assertEqual(normalize("pct", 0), (None, None))
        self.assertEqual(normalize("linh tinh", 5), (None, None))
        self.assertEqual(normalize("day", "abc"), (None, None))

    def test_nhan_ngan(self):
        self.assertEqual(calc_label("pct", 10), "10% lương gốc")
        self.assertEqual(calc_label("day", 20_000), "20.000đ × ngày công")
        self.assertEqual(calc_label(None, None), "")


class AllowanceRecalcTest(unittest.TestCase):
    """Số phụ cấp phải ĐỔI THEO khi lương gốc / ngày công đổi."""

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        ensure_table(self.conn)
        salary_store.ensure_schema(self.conn)
        attendance_store.ensure_schema(self.conn)
        # có thợ lương SP thì compute_range_report đụng các bảng sản xuất — dựng
        # tối thiểu như tests/test_salary_store.py
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS production_report_rows (thread_id INTEGER,"
            " report_ymd TEXT, worker_id INTEGER, worker_name TEXT, product_id INTEGER,"
            " product_code TEXT, tong_calc REAL, so_gio REAL)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, code TEXT)")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS production_slips (thread_id INTEGER PRIMARY KEY,"
            " sp_name TEXT, luong_1sp REAL, kind TEXT, bang TEXT)")
        from production_store.allowances import ensure_schema as ens_allow
        ens_allow(self.conn)
        self.a = add_worker(self.conn, "An")["id"]
        update_worker(self.conn, self.a, wage_type="time", monthly_salary=5_200_000)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def _row(self, ym="2026-08"):
        d = salary_store.compute_month_payroll(self.conn, ym)
        return next(r for r in d["workers"] if r["worker_id"] == self.a)

    def _cham(self, ngay, code="77"):
        attendance_store.map_employee_code(self.conn, code, self.a)
        for day in ngay:
            for t in ("07:00", "11:00", "13:00", "17:00"):
                attendance_store.add_manual(self.conn, code, day, t)

    def test_pct_chay_theo_luong_ngay_cong(self):
        # thợ TG: gốc = lương theo ngày công = mốc/26 × công
        self._cham(["2026-08-03", "2026-08-04"])            # 2 công
        salary_store.add_allowance(self.conn, self.a, "2026-08", 0, calc_kind="pct", calc_value=10)
        r1 = self._row()
        self.assertEqual(r1["phu_cap"], round(r1["luong_cong"] * 0.10))
        # CHẤM THÊM 2 ngày → lương gốc tăng → phụ cấp PHẢI tăng theo
        self._cham(["2026-08-05", "2026-08-06"])
        r2 = self._row()
        self.assertGreater(r2["luong_cong"], r1["luong_cong"])
        self.assertEqual(r2["phu_cap"], round(r2["luong_cong"] * 0.10))
        self.assertGreater(r2["phu_cap"], r1["phu_cap"])

    def test_day_chay_theo_so_ngay_cong(self):
        self._cham(["2026-08-03", "2026-08-04"])            # 2 công
        salary_store.add_allowance(self.conn, self.a, "2026-08", 0, calc_kind="day", calc_value=20_000)
        self.assertEqual(self._row()["phu_cap"], 40_000)
        self._cham(["2026-08-05"])                          # thành 3 công
        self.assertEqual(self._row()["phu_cap"], 60_000)

    def test_tien_co_dinh_van_dung_yen(self):
        self._cham(["2026-08-03"])
        salary_store.add_allowance(self.conn, self.a, "2026-08", 300_000, note="Ăn trưa")
        self.assertEqual(self._row()["phu_cap"], 300_000)
        self._cham(["2026-08-04", "2026-08-05"])            # lương gốc đổi
        self.assertEqual(self._row()["phu_cap"], 300_000)   # vẫn nguyên

    def test_tron_ca_3_dang(self):
        self._cham(["2026-08-03", "2026-08-04"])
        salary_store.add_allowance(self.conn, self.a, "2026-08", 300_000, note="Ăn trưa")
        salary_store.add_allowance(self.conn, self.a, "2026-08", 0, calc_kind="day", calc_value=20_000)
        salary_store.add_allowance(self.conn, self.a, "2026-08", 0, calc_kind="pct", calc_value=10)
        r = self._row()
        self.assertEqual(r["pc_count"], 3)
        self.assertEqual(r["phu_cap"], 300_000 + 40_000 + round(r["luong_cong"] * 0.10))

    def test_vo_hieu_thi_khong_tinh_nua(self):
        self._cham(["2026-08-03"])
        got = salary_store.add_allowance(self.conn, self.a, "2026-08", 0, calc_kind="day", calc_value=20_000)
        self.assertEqual(self._row()["phu_cap"], 20_000)
        salary_store.void_allowance(self.conn, got["id"], "ghi nhầm")
        self.assertEqual(self._row()["phu_cap"], 0)

    def test_list_tra_so_da_tinh_lai_khi_biet_goc(self):
        self._cham(["2026-08-03", "2026-08-04"])
        salary_store.add_allowance(self.conn, self.a, "2026-08", 0, calc_kind="day", calc_value=20_000)
        rows = salary_store.list_allowances(self.conn, "2026-08", self.a, base=0, cong=2)
        self.assertEqual(rows[0]["amount"], 40_000)
        self.assertEqual(rows[0]["calc_kind"], "day")
        self.assertEqual(rows[0]["calc_label"], "20.000đ × ngày công")

    def test_tho_luong_sp_lay_goc_la_luong_san_pham(self):
        b = add_worker(self.conn, "Bình")["id"]
        update_worker(self.conn, b, wage_type="product")
        self.conn.execute("INSERT INTO products (code) VALUES ('SP1')")
        pid = self.conn.execute("SELECT id FROM products WHERE code='SP1'").fetchone()[0]
        self.conn.execute("INSERT INTO production_slips (thread_id, sp_name, luong_1sp, kind, bang) "
                          "VALUES (901, 'SP1', 1000, 'san_xuat', '{}')")
        self.conn.execute("INSERT INTO production_report_rows (thread_id, report_ymd, worker_id,"
                          " worker_name, product_id, product_code, tong_calc, so_gio) "
                          "VALUES (901, '2026-08-03', ?, 'Bình', ?, 'SP1', 100, 0)", (b, pid))
        self.conn.commit()
        salary_store.add_allowance(self.conn, b, "2026-08", 0, calc_kind="pct", calc_value=10)
        d = salary_store.compute_month_payroll(self.conn, "2026-08")
        r = next(x for x in d["workers"] if x["worker_id"] == b)
        self.assertEqual(r["luong_sp"], 100_000)          # 100 cây × 1.000đ
        self.assertEqual(r["phu_cap"], 10_000)            # 10% lương SP


if __name__ == "__main__":
    unittest.main()
