"""Test lương THÁNG (salary_store): phụ cấp/thưởng upsert, ứng nhiều lần cộng dồn,
thực lãnh = lương + phụ cấp + thưởng − ứng. Thợ 'time' → lương SP = 0 (chờ chấm công).
"""
from __future__ import annotations

import os
import tempfile
import unittest

import salary_store
from utils.db import get_connection
from worker_store import add_worker, ensure_table, update_worker


class SalaryStoreTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        ensure_table(self.conn)
        salary_store.ensure_schema(self.conn)
        # bảng sản xuất tối thiểu để compute_range_report chạy (lương SP thợ 'product')
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS production_report_rows (thread_id INTEGER, report_ymd TEXT,"
            " worker_id INTEGER, worker_name TEXT, product_id INTEGER, product_code TEXT,"
            " tong_calc REAL, so_gio REAL)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, code TEXT)")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS production_slips (thread_id INTEGER PRIMARY KEY, sp_name TEXT,"
            " luong_1sp REAL, kind TEXT, bang TEXT)")
        from production_store.allowances import ensure_schema as ens_allow
        ens_allow(self.conn)
        # 2 thợ 'time' (lương SP = 0, không phụ thuộc dữ liệu sản xuất)
        self.a = add_worker(self.conn, "An")["id"]
        self.b = add_worker(self.conn, "Bình")["id"]
        update_worker(self.conn, self.a, wage_type="time")
        update_worker(self.conn, self.b, wage_type="time")

    def _seed_product_worker(self, name, tong_calc=10, gia=1000):
        """Thợ SP + 1 phiếu sản xuất → lương = tong_calc × gia. Trả worker_id."""
        wid = add_worker(self.conn, name)["id"]
        update_worker(self.conn, wid, wage_type="product")
        self.conn.execute("INSERT INTO products (code) VALUES ('SP1')")
        pid = self.conn.execute("SELECT id FROM products WHERE code='SP1'").fetchone()[0]
        self.conn.execute(
            "INSERT INTO production_report_rows (thread_id, report_ymd, worker_id, worker_name,"
            " product_id, product_code, tong_calc) VALUES (100,'2026-07-07',?,?,?,'SP1',?)",
            (wid, name, pid, tong_calc))
        self.conn.execute(
            "INSERT INTO production_slips (thread_id, sp_name, luong_1sp, kind, bang)"
            " VALUES (100,'SP1',?,'san_xuat','{}')", (gia,))
        self.conn.commit()
        return wid

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def _row(self, data, wid):
        return next(r for r in data["workers"] if r["worker_id"] == wid)

    def test_month_range(self):
        self.assertEqual(salary_store.month_range("2026-02"), ("2026-02-01", "2026-02-28"))
        self.assertEqual(salary_store.month_range("2026-07"), ("2026-07-01", "2026-07-31"))

    def test_time_worker_luong_0_va_phu_cap_thuong(self):
        salary_store.add_allowance(self.conn, self.a, "2026-07", 100_000, note="ăn trưa")
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, thuong=50_000)
        d = salary_store.compute_month_payroll(self.conn, "2026-07")
        r = self._row(d, self.a)
        self.assertEqual(r["wage_type"], "time")
        self.assertEqual(r["luong"], 0)              # thời gian → 0
        self.assertEqual(r["phu_cap"], 100_000)
        self.assertEqual(r["pc_count"], 1)
        self.assertEqual(r["thuong"], 50_000)
        self.assertEqual(r["thuc_lanh"], 150_000)    # 0 + 100k + 50k − 0

    def test_time_worker_luong_tu_cham_cong(self):
        """Lương TG = mốc/26 × công + tăng ca ×1,2 (công/TC từ máy chấm công)."""
        import attendance_store
        attendance_store.ensure_schema(self.conn)
        update_worker(self.conn, self.a, monthly_salary=5_200_000)
        attendance_store.map_employee_code(self.conn, "77", self.a)
        # ngày 1: đủ 2 ca = 1 công → 5.2tr/26 = 200k
        for t in ("07:00", "11:00", "13:00", "17:00"):
            attendance_store.add_manual(self.conn, "77", "2026-07-06", t)
        # ngày 2: đủ 2 ca + tăng ca tới 19:00 (120ph ×1,2) → 200k + 200k/480×120×1.2 = 260k
        for t in ("07:00", "11:00", "13:00", "19:00"):
            attendance_store.add_manual(self.conn, "77", "2026-07-07", t)
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertEqual(r["monthly_salary"], 5_200_000)
        self.assertEqual(r["cong"], 2.0)
        self.assertEqual(r["ot_gio"], 2.0)
        self.assertEqual(r["luong_cong"], 400_000)   # 2 công × 200k
        self.assertEqual(r["luong_tc"], 60_000)      # 2g TC × 25k/g ×1,2
        self.assertEqual(r["luong"], 460_000)
        self.assertEqual(r["thuc_lanh"], 460_000)

    def test_adjust_upsert_giu_field_khong_truyen(self):
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, thuong=100_000)
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, weekly=True)  # không đụng thuong
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertEqual(r["thuong"], 100_000)
        self.assertTrue(r["weekly"])

    def test_phu_cap_nhieu_khoan_cong_don(self):
        salary_store.add_allowance(self.conn, self.a, "2026-07", 100_000, note="ăn trưa")
        salary_store.add_allowance(self.conn, self.a, "2026-07", 50_000, note="xăng xe")
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertEqual(r["phu_cap"], 150_000)      # cộng dồn các khoản
        self.assertEqual(r["pc_count"], 2)
        self.assertEqual(r["thuc_lanh"], 150_000)    # time worker: 0 + 150k

    def test_vo_hieu_khoan_phu_cap_hoan_lai_nhung_giu_dong(self):
        a1 = salary_store.add_allowance(self.conn, self.b, "2026-07", 30_000)
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.b)["phu_cap"], 30_000)
        self.assertTrue(salary_store.void_allowance(self.conn, a1["id"], "ghi nhầm", by="duy"))
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.b)["phu_cap"], 0)
        rows = salary_store.list_allowances(self.conn, "2026-07", self.b)
        self.assertEqual(len(rows), 1)                       # dòng vẫn còn để đối chiếu
        self.assertTrue(rows[0]["voided_at"])
        self.assertEqual(rows[0]["voided_by"], "duy")
        self.assertEqual(rows[0]["void_reason"], "ghi nhầm")
        # vô hiệu lần 2 → False (đã vô hiệu rồi)
        self.assertFalse(salary_store.void_allowance(self.conn, a1["id"], "lần 2"))

    def test_vo_hieu_phai_co_ly_do(self):
        a1 = salary_store.add_allowance(self.conn, self.b, "2026-07", 30_000)
        with self.assertRaises(ValueError):
            salary_store.void_allowance(self.conn, a1["id"], "  ")
        adv = salary_store.add_advance(self.conn, self.b, "2026-07", 10_000)
        with self.assertRaises(ValueError):
            salary_store.void_advance(self.conn, adv["id"], "")

    def test_phu_cap_amount_phai_duong(self):
        with self.assertRaises(ValueError):
            salary_store.add_allowance(self.conn, self.a, "2026-07", 0)

    def test_ung_nhieu_lan_cong_don_va_tru(self):
        salary_store.add_allowance(self.conn, self.a, "2026-07", 200_000)
        salary_store.add_advance(self.conn, self.a, "2026-07", 30_000, adv_date="2026-07-05")
        salary_store.add_advance(self.conn, self.a, "2026-07", 20_000, adv_date="2026-07-10")
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertEqual(r["ung"], 50_000)
        self.assertEqual(r["adv_count"], 2)
        self.assertEqual(r["thuc_lanh"], 150_000)    # 0 + 200k − 50k

    def test_vo_hieu_ung_hoan_lai_nhung_giu_dong(self):
        adv = salary_store.add_advance(self.conn, self.b, "2026-07", 40_000)
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.b)["ung"], 40_000)
        self.assertTrue(salary_store.void_advance(self.conn, adv["id"], "ứng nhầm người", by="trang"))
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.b)["ung"], 0)
        rows = salary_store.list_advances(self.conn, "2026-07", self.b)
        self.assertEqual(len(rows), 1)                       # dòng vẫn còn để đối chiếu
        self.assertTrue(rows[0]["voided_at"])
        self.assertEqual(rows[0]["voided_by"], "trang")
        self.assertEqual(rows[0]["void_reason"], "ứng nhầm người")
        self.assertFalse(salary_store.void_advance(self.conn, adv["id"], "lần 2"))
        self.assertFalse(salary_store.void_advance(self.conn, 99_999, "không tồn tại"))

    def test_advance_amount_phai_duong(self):
        with self.assertRaises(ValueError):
            salary_store.add_advance(self.conn, self.a, "2026-07", 0)

    def test_nhan_luong_tuan_tu_dong_ung_bang_luong_sp(self):
        # Thợ SP lương 10.000, bật nhận lương tuần → ứng tự động = 10.000
        c = self._seed_product_worker("Chi", tong_calc=10, gia=1000)
        salary_store.set_month_adjust(self.conn, "2026-07", c, weekly=True)
        salary_store.add_allowance(self.conn, c, "2026-07", 2_000)
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), c)
        self.assertTrue(r["weekly"])
        self.assertEqual(r["luong"], 10_000)
        self.assertEqual(r["ung_weekly"], 10_000)   # ứng tự động = đúng lương SP
        self.assertEqual(r["ung"], 10_000)          # chưa có ứng tay
        self.assertEqual(r["thuc_lanh"], 2_000)     # 10k + 2k − 10k = 2k (phụ cấp)

    def test_luong_tuan_cong_don_voi_ung_tay(self):
        c = self._seed_product_worker("Chi", tong_calc=10, gia=1000)  # lương 10k
        salary_store.set_month_adjust(self.conn, "2026-07", c, weekly=True)
        salary_store.add_advance(self.conn, c, "2026-07", 3_000)      # ứng tay thêm
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), c)
        self.assertEqual(r["ung_weekly"], 10_000)
        self.assertEqual(r["ung"], 13_000)          # 10k tuần + 3k tay
        self.assertEqual(r["thuc_lanh"], -3_000)    # 10k − 13k

    def test_khong_nhan_luong_tuan_khong_ung_tu_dong(self):
        c = self._seed_product_worker("Chi", tong_calc=10, gia=1000)  # weekly mặc định off
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), c)
        self.assertFalse(r["weekly"])
        self.assertEqual(r["ung_weekly"], 0)
        self.assertEqual(r["thuc_lanh"], 10_000)    # nhận đủ lương

    def test_luong_tuan_thoi_gian_khong_anh_huong(self):
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, weekly=True)   # a là thợ 'time' (lương 0)
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertTrue(r["weekly"])
        self.assertEqual(r["ung_weekly"], 0)        # lương thời gian = 0 → không ứng tự động

    def test_ung_tach_theo_thang(self):
        salary_store.add_advance(self.conn, self.a, "2026-07", 10_000)
        salary_store.add_advance(self.conn, self.a, "2026-08", 99_000)
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)["ung"], 10_000)
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-08"), self.a)["ung"], 99_000)


if __name__ == "__main__":
    unittest.main()
