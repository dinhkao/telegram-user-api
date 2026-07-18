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
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, phu_cap=100_000, thuong=50_000)
        d = salary_store.compute_month_payroll(self.conn, "2026-07")
        r = self._row(d, self.a)
        self.assertEqual(r["wage_type"], "time")
        self.assertEqual(r["luong"], 0)              # thời gian → 0
        self.assertEqual(r["phu_cap"], 100_000)
        self.assertEqual(r["thuong"], 50_000)
        self.assertEqual(r["thuc_lanh"], 150_000)    # 0 + 100k + 50k − 0

    def test_adjust_upsert_giu_field_khong_truyen(self):
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, phu_cap=100_000)
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, thuong=20_000)  # không đụng phu_cap
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertEqual(r["phu_cap"], 100_000)
        self.assertEqual(r["thuong"], 20_000)

    def test_ung_nhieu_lan_cong_don_va_tru(self):
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, phu_cap=200_000)
        salary_store.add_advance(self.conn, self.a, "2026-07", 30_000, adv_date="2026-07-05")
        salary_store.add_advance(self.conn, self.a, "2026-07", 20_000, adv_date="2026-07-10")
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertEqual(r["ung"], 50_000)
        self.assertEqual(r["adv_count"], 2)
        self.assertEqual(r["thuc_lanh"], 150_000)    # 0 + 200k − 50k

    def test_xoa_ung_hoan_lai(self):
        adv = salary_store.add_advance(self.conn, self.b, "2026-07", 40_000)
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.b)["ung"], 40_000)
        self.assertTrue(salary_store.delete_advance(self.conn, adv["id"]))
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.b)["ung"], 0)

    def test_advance_amount_phai_duong(self):
        with self.assertRaises(ValueError):
            salary_store.add_advance(self.conn, self.a, "2026-07", 0)

    def test_nhan_luong_tuan_tu_dong_ung_bang_luong_sp(self):
        # Thợ SP lương 10.000, bật nhận lương tuần → ứng tự động = 10.000
        c = self._seed_product_worker("Chi", tong_calc=10, gia=1000)
        update_worker(self.conn, c, weekly_salary=True)
        salary_store.set_month_adjust(self.conn, "2026-07", c, phu_cap=2_000)
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), c)
        self.assertTrue(r["weekly_salary"])
        self.assertEqual(r["luong"], 10_000)
        self.assertEqual(r["ung_weekly"], 10_000)   # ứng tự động = đúng lương SP
        self.assertEqual(r["ung"], 10_000)          # chưa có ứng tay
        self.assertEqual(r["thuc_lanh"], 2_000)     # 10k + 2k − 10k = 2k (phụ cấp)

    def test_luong_tuan_cong_don_voi_ung_tay(self):
        c = self._seed_product_worker("Chi", tong_calc=10, gia=1000)  # lương 10k
        update_worker(self.conn, c, weekly_salary=True)
        salary_store.add_advance(self.conn, c, "2026-07", 3_000)      # ứng tay thêm
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), c)
        self.assertEqual(r["ung_weekly"], 10_000)
        self.assertEqual(r["ung"], 13_000)          # 10k tuần + 3k tay
        self.assertEqual(r["thuc_lanh"], -3_000)    # 10k − 13k

    def test_khong_nhan_luong_tuan_khong_ung_tu_dong(self):
        c = self._seed_product_worker("Chi", tong_calc=10, gia=1000)  # weekly mặc định off
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), c)
        self.assertFalse(r["weekly_salary"])
        self.assertEqual(r["ung_weekly"], 0)
        self.assertEqual(r["thuc_lanh"], 10_000)    # nhận đủ lương

    def test_luong_tuan_thoi_gian_khong_anh_huong(self):
        update_worker(self.conn, self.a, weekly_salary=True)   # a là thợ 'time' (lương 0)
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertTrue(r["weekly_salary"])
        self.assertEqual(r["ung_weekly"], 0)        # lương thời gian = 0 → không ứng tự động

    def test_ung_tach_theo_thang(self):
        salary_store.add_advance(self.conn, self.a, "2026-07", 10_000)
        salary_store.add_advance(self.conn, self.a, "2026-08", 99_000)
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)["ung"], 10_000)
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-08"), self.a)["ung"], 99_000)


if __name__ == "__main__":
    unittest.main()
