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

    def test_tg_sao_gop_gio_tang_ca_vao_ngay_cong(self):
        """TG* ('time_flat'): trả CỐ ĐỊNH theo ngày công, giờ tăng ca GỘP vào công —
        không có lương tăng ca ×1,2 riêng. So sánh thẳng với TG cùng dữ liệu chấm công."""
        import attendance_store
        attendance_store.ensure_schema(self.conn)
        # 2 thợ cùng mốc 5.200.000 (200k/công, 25k/giờ) và CÙNG giờ chấm công
        update_worker(self.conn, self.a, wage_type="time", monthly_salary=5_200_000)
        update_worker(self.conn, self.b, wage_type="time_flat", monthly_salary=5_200_000)
        for code, wid in (("77", self.a), ("88", self.b)):
            attendance_store.map_employee_code(self.conn, code, wid)
            for day in ("2026-07-06", "2026-07-07"):
                # ngày 1: đủ 2 ca (1 công). ngày 2: đủ 2 ca + tăng ca tới 19:00 (2 giờ)
                for t in ("07:00", "11:00", "13:00", "17:00" if day.endswith("06") else "19:00"):
                    attendance_store.add_manual(self.conn, code, day, t)
        d = salary_store.compute_month_payroll(self.conn, "2026-07")
        tg, tgx = self._row(d, self.a), self._row(d, self.b)
        # TG: 2 công + 2 giờ TC tính riêng ×1,2
        self.assertEqual((tg["cong"], tg["ot_gio"]), (2.0, 2.0))
        self.assertEqual((tg["luong_cong"], tg["luong_tc"], tg["luong"]), (400_000, 60_000, 460_000))
        # TG*: 2 công + 2 giờ TC = 2,25 công (2g = 0,25 ngày 8 giờ), KHÔNG có lương TC
        self.assertEqual((tgx["cong"], tgx["ot_gio"]), (2.25, 2.0))
        self.assertEqual(tgx["luong_tc"], 0)
        self.assertEqual((tgx["luong_cong"], tgx["luong"]), (450_000, 450_000))   # 200k × 2,25
        self.assertEqual(tgx["wage_type"], "time_flat")
        # TG* KHÔNG ăn lương sản phẩm (chỉ thợ 'product' vào compute_range_report)
        self.assertEqual(tgx["pc_phieu"], 0)

    def test_tg_sao_khong_co_tang_ca_thi_giong_tg(self):
        """Không có giờ tăng ca → TG* và TG ra cùng số (khác biệt chỉ ở phần TC)."""
        import attendance_store
        attendance_store.ensure_schema(self.conn)
        update_worker(self.conn, self.b, wage_type="time_flat", monthly_salary=5_200_000)
        attendance_store.map_employee_code(self.conn, "88", self.b)
        for t in ("07:00", "11:00", "13:00", "17:00"):
            attendance_store.add_manual(self.conn, "88", "2026-07-06", t)
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.b)
        self.assertEqual((r["cong"], r["ot_gio"]), (1.0, 0.0))
        self.assertEqual((r["luong_cong"], r["luong_tc"], r["luong"]), (200_000, 0, 200_000))

    def test_adjust_upsert_giu_field_khong_truyen(self):
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, thuong=100_000)
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, weekly=True)  # không đụng thuong
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertEqual(r["thuong"], 100_000)
        self.assertTrue(r["weekly"])

    def test_luong_cho_hang_cong_vao_thuc_lanh_va_khong_ke_thua(self):
        """Lương chờ hàng = khoản CỘNG gõ tay của TỪNG THÁNG. 0 = xoá; tháng sau
        KHÔNG tự kế thừa (giống thưởng, khác mốc/BHXH)."""
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, cho_hang=300_000)
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertEqual(r["cho_hang"], 300_000)
        self.assertEqual(r["thuc_lanh"], 300_000)
        self.assertEqual(salary_store.compute_month_payroll(self.conn, "2026-07")["totals"]["cho_hang"],
                         300_000)
        # tháng sau: không kế thừa
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-08"), self.a)["cho_hang"], 0)
        # sửa field khác KHÔNG được xoá mất khoản chờ hàng đã ghi
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, weekly=True)
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)["cho_hang"],
                         300_000)
        # 0 = xoá
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, cho_hang=0)
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertEqual(r["cho_hang"], 0)
        self.assertEqual(r["thuc_lanh"], 0)

    def test_ngay_cong_go_tay_de_so_may_cham(self):
        """Ghi đè ngày công: đè hẳn số máy chấm, kéo theo mọi thứ ăn theo công
        (lương ngày công, thưởng vệ sinh); None = bỏ đè, quay về số máy."""
        update_worker(self.conn, self.a, wage_type="time", monthly_salary=5_200_000)
        r0 = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertFalse(r0["cong_manual"])
        salary_store.set_cong_override(self.conn, "2026-07", self.a, 26)
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertEqual(r["cong"], 26)
        self.assertTrue(r["cong_manual"])
        self.assertEqual(r["cong_auto"], r0["cong"])       # số máy chấm vẫn giữ để đối chiếu
        self.assertEqual(r["luong_cong"], 5_200_000)       # 5.2tr/26 × 26 công
        # 0 là số CÓ NGHĨA (ép 0 công), khác hẳn "bỏ ghi đè"
        salary_store.set_cong_override(self.conn, "2026-07", self.a, 0)
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertEqual(r["cong"], 0)
        self.assertTrue(r["cong_manual"])
        salary_store.set_cong_override(self.conn, "2026-07", self.a, None)
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertFalse(r["cong_manual"])
        self.assertEqual(r["cong"], r0["cong"])
        # KHÔNG kế thừa sang tháng sau
        salary_store.set_cong_override(self.conn, "2026-07", self.a, 20)
        self.assertFalse(self._row(salary_store.compute_month_payroll(self.conn, "2026-08"), self.a)["cong_manual"])

    def test_so_tru_an_tru_thang_vao_luong_sp(self):
        """Trừ ẩn: lương SP giảm ĐÚNG số đó, thực lãnh giảm y hệt, giữ luong_goc để
        đối chiếu. Trừ quá lương thì kẹp ở 0 (không cho lương âm)."""
        wid = self._seed_product_worker("Cường", tong_calc=1000, gia=1000)   # lương SP = 1tr
        salary_store.set_month_adjust(self.conn, "2026-07", wid, tru_an=200_000)
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), wid)
        self.assertEqual(r["tru_an"], 200_000)
        self.assertEqual(r["luong_goc"], 1_000_000)
        self.assertEqual(r["luong_goc"] - r["luong_sp"], 200_000)
        self.assertEqual(r["luong_sp"], r["luong"])
        # kẹp ở 0, không âm
        salary_store.set_month_adjust(self.conn, "2026-07", wid, tru_an=99_000_000)
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), wid)
        self.assertEqual(r["luong_sp"], 0)
        # 0 = bỏ
        salary_store.set_month_adjust(self.conn, "2026-07", wid, tru_an=0)
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), wid)
        self.assertEqual(r["tru_an"], 0)
        self.assertEqual(r["luong_sp"], r["luong_goc"])

    def test_tru_an_khong_keo_phu_cap_phan_tram_xuong(self):
        """Phụ cấp % tính trên lương TRƯỚC khi trừ ẩn → thực lãnh giảm ĐÚNG bằng số
        trừ, không nhân thêm hệ số nào."""
        wid = self._seed_product_worker("Dũng", tong_calc=1000, gia=1000)    # lương SP = 1tr
        salary_store.add_allowance(self.conn, wid, "2026-07", 0, note="10%",
                                   calc_kind="pct", calc_value=10)
        before = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), wid)
        self.assertEqual(before["phu_cap"], 100_000)        # 10% của 1tr
        salary_store.set_month_adjust(self.conn, "2026-07", wid, tru_an=100_000)
        after = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), wid)
        self.assertEqual(after["phu_cap"], before["phu_cap"])          # phụ cấp % KHÔNG đổi
        self.assertEqual(before["thuc_lanh"] - after["thuc_lanh"], 100_000)

    def test_luong_tuan_ap_cho_ca_2_loai_luong(self):
        """NHẬN LƯƠNG TUẦN áp cho CẢ lương SP lẫn lương THỜI GIAN (Duy chốt
        2026-08-05): ứng tự động = đúng lương của tháng → phần lương khử hết,
        thực lãnh chỉ còn các khoản khác."""
        import attendance_store
        attendance_store.ensure_schema(self.conn)
        update_worker(self.conn, self.a, wage_type="time", monthly_salary=5_200_000)
        attendance_store.map_employee_code(self.conn, "77", self.a)
        for t in ("07:00", "11:00", "13:00", "17:00"):
            attendance_store.add_manual(self.conn, "77", "2026-07-06", t)
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, weekly=True)
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertEqual(r["luong"], 200_000)          # 1 công × 200k
        self.assertEqual(r["ung_weekly"], 200_000)     # thợ TG cũng ăn luật lương tuần
        self.assertEqual(r["thuc_lanh"], 0)

    def test_luong_tuan_khong_nuot_mat_so_tru_an(self):
        """Thợ nhận lương tuần MÀ có số trừ ẩn: ứng tự động phải lấy lương TRƯỚC khi
        trừ (= số đã trả trong tháng) → thực lãnh ÂM đúng bằng số trừ. Lấy lương
        sau-trừ thì 2 số khử nhau, gõ trừ ẩn xong thực lãnh đứng im."""
        wid = self._seed_product_worker("Em", tong_calc=1000, gia=1000)   # lương SP 1tr
        salary_store.set_month_adjust(self.conn, "2026-07", wid, weekly=True)
        r0 = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), wid)
        self.assertEqual((r0["luong"], r0["ung_weekly"], r0["thuc_lanh"]), (1_000_000, 1_000_000, 0))
        salary_store.set_month_adjust(self.conn, "2026-07", wid, tru_an=300_000)
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), wid)
        self.assertEqual(r["luong"], 700_000)          # lương SP đã trừ
        self.assertEqual(r["ung_weekly"], 1_000_000)   # đã trả nguyên lương theo tuần
        self.assertEqual(r["thuc_lanh"], -300_000)     # còn nợ đúng số trừ ẩn

    def test_tong_thuc_lanh_khong_cong_tho_am(self):
        """TỔNG cột Lãnh = tiền THỰC phải chi → chỉ cộng thợ dương (Duy chốt
        2026-08-05). Thợ âm (ứng vượt lương) nhận 0 và nợ lại, gom riêng ở
        thuc_lanh_am/am_count chứ không trừ vào tổng."""
        salary_store.add_allowance(self.conn, self.a, "2026-07", 500_000, note="phụ cấp")
        salary_store.add_advance(self.conn, self.b, "2026-07", 800_000)   # b không có lương → âm
        t = salary_store.compute_month_payroll(self.conn, "2026-07")["totals"]
        self.assertEqual(t["thuc_lanh"], 500_000)        # KHÔNG bị 800k của b kéo xuống
        self.assertEqual(t["thuc_lanh_am"], 800_000)     # phần âm gom riêng (số dương)
        self.assertEqual(t["am_count"], 1)

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

    def test_sua_ghi_chu_khoan_phu_cap_va_ung(self):
        al = salary_store.add_allowance(self.conn, self.a, "2026-07", 80_000, note="ăn trưa")
        adv = salary_store.add_advance(self.conn, self.a, "2026-07", 20_000, adv_date="2026-07-05", note="")
        self.assertTrue(salary_store.update_allowance_note(self.conn, al["id"], "  ăn trưa T7  "))
        self.assertTrue(salary_store.update_advance_note(self.conn, adv["id"], "ứng mua xe"))
        arow = salary_store.list_allowances(self.conn, "2026-07", self.a)[0]
        drow = salary_store.list_advances(self.conn, "2026-07", self.a)[0]
        self.assertEqual(arow["note"], "ăn trưa T7")     # trim khoảng trắng
        self.assertEqual(drow["note"], "ứng mua xe")
        # SỐ TIỀN + ngày KHÔNG đổi khi sửa ghi chú
        self.assertEqual(arow["amount"], 80_000)
        self.assertEqual(drow["amount"], 20_000)
        self.assertEqual(drow["adv_date"], "2026-07-05")
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)
        self.assertEqual(r["phu_cap"], 80_000)
        self.assertEqual(r["ung"], 20_000)
        # xoá trắng ghi chú được
        self.assertTrue(salary_store.update_advance_note(self.conn, adv["id"], ""))
        self.assertEqual(salary_store.list_advances(self.conn, "2026-07", self.a)[0]["note"], "")

    def test_khong_sua_ghi_chu_khoan_da_vo_hieu_hoac_khong_ton_tai(self):
        al = salary_store.add_allowance(self.conn, self.b, "2026-07", 10_000, note="xăng xe")
        adv = salary_store.add_advance(self.conn, self.b, "2026-07", 10_000, note="ứng")
        salary_store.void_allowance(self.conn, al["id"], "ghi nhầm")
        salary_store.void_advance(self.conn, adv["id"], "ghi nhầm")
        self.assertFalse(salary_store.update_allowance_note(self.conn, al["id"], "sửa"))
        self.assertFalse(salary_store.update_advance_note(self.conn, adv["id"], "sửa"))
        self.assertFalse(salary_store.update_allowance_note(self.conn, 99_999, "sửa"))
        self.assertFalse(salary_store.update_advance_note(self.conn, 99_999, "sửa"))
        # ghi chú dòng đã vô hiệu giữ NGUYÊN
        self.assertEqual(salary_store.list_allowances(self.conn, "2026-07", self.b)[0]["note"], "xăng xe")
        self.assertEqual(salary_store.list_advances(self.conn, "2026-07", self.b)[0]["note"], "ứng")

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

    def test_luong_sp_gom_phu_cap_phieu_va_tach_rieng_pc_phieu(self):
        """Lương SP = tiền cây + PHỤ CẤP GHI TRONG PHIẾU SX (production_allowances);
        `pc_phieu` báo riêng phần đã gộp đó (KHÁC phu_cap = phụ cấp THÁNG) — người dùng
        tưởng bảng lương bỏ sót phụ cấp phiếu vì nó chìm trong cột Lương."""
        from production_store.allowances import set_allowance
        c = self._seed_product_worker("Chi", tong_calc=10, gia=1000)     # tiền cây 10.000
        set_allowance(self.conn, 100, "Chi", 7_000)                      # phụ cấp phiếu 100
        salary_store.add_allowance(self.conn, c, "2026-07", 2_000)       # phụ cấp THÁNG
        r = self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), c)
        self.assertEqual(r["luong"], 17_000)        # 10k cây + 7k phụ cấp phiếu
        self.assertEqual(r["pc_phieu"], 7_000)      # phần phụ cấp phiếu ĐÃ nằm trong luong
        self.assertEqual(r["phu_cap"], 2_000)       # phụ cấp tháng tách riêng
        self.assertEqual(r["thuc_lanh"], 19_000)    # 17k + 2k (không cộng phụ cấp phiếu 2 lần)
        # thợ lương THỜI GIAN không dính phụ cấp phiếu
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-07"),
                                   self.a)["pc_phieu"], 0)

    def test_ung_tach_theo_thang(self):
        salary_store.add_advance(self.conn, self.a, "2026-07", 10_000)
        salary_store.add_advance(self.conn, self.a, "2026-08", 99_000)
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-07"), self.a)["ung"], 10_000)
        self.assertEqual(self._row(salary_store.compute_month_payroll(self.conn, "2026-08"), self.a)["ung"], 99_000)


if __name__ == "__main__":
    unittest.main()
