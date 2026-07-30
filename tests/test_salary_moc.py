"""Test MỐC LƯƠNG THÁNG theo TỪNG THÁNG (salary_store/moc.py).

Luật: mốc đặt ở tháng nào thì áp từ tháng đó TRỞ ĐI (tháng sau tự kế thừa), tháng
TRƯỚC không đổi; chưa đặt bao giờ → mốc hồ sơ thợ. Mục đích: sửa mốc hôm nay KHÔNG
tính lại bảng lương tháng cũ đã trả tiền.
"""
from __future__ import annotations

import os
import tempfile
import unittest

import attendance_store
import salary_store
from utils.db import get_connection
from worker_store import add_worker, ensure_table, update_worker


class SalaryMocTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        ensure_table(self.conn)
        salary_store.ensure_schema(self.conn)
        attendance_store.ensure_schema(self.conn)
        self.a = add_worker(self.conn, "An")["id"]
        update_worker(self.conn, self.a, wage_type="time", monthly_salary=6_500_000)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def _row(self, ym):
        d = salary_store.compute_month_payroll(self.conn, ym)
        return next(r for r in d["workers"] if r["worker_id"] == self.a)

    def _cham_cong(self, day: str, code: str = "77"):
        """1 ngày đủ 2 ca = 1 công (không tăng ca)."""
        attendance_store.map_employee_code(self.conn, code, self.a)
        for t in ("07:00", "11:00", "13:00", "17:00"):
            attendance_store.add_manual(self.conn, code, day, t)

    # ── luật kế thừa / không đụng quá khứ ────────────────────────────────────────

    def test_chua_dat_thi_dung_moc_ho_so_tho(self):
        r = self._row("2026-07")
        self.assertEqual(r["monthly_salary"], 6_500_000)
        self.assertEqual(r["moc_ym"], "")      # không phải mốc của tháng nào
        self.assertFalse(r["moc_own"])

    def test_dat_thang_nao_ap_tu_thang_do_tro_di(self):
        salary_store.set_month_moc(self.conn, "2026-07", self.a, 7_500_000, by="duy")
        self.assertEqual(self._row("2026-06")["monthly_salary"], 6_500_000)   # QUÁ KHỨ không đổi
        r7 = self._row("2026-07")
        self.assertEqual(r7["monthly_salary"], 7_500_000)
        self.assertEqual(r7["moc_ym"], "2026-07")
        self.assertTrue(r7["moc_own"])                                        # đặt riêng tháng này
        r8 = self._row("2026-08")
        self.assertEqual(r8["monthly_salary"], 7_500_000)                     # tháng sau KẾ THỪA
        self.assertEqual(r8["moc_ym"], "2026-07")
        self.assertFalse(r8["moc_own"])                                       # không phải mốc riêng

    def test_moi_thang_mot_so_khac_nhau(self):
        salary_store.set_month_moc(self.conn, "2026-07", self.a, 7_500_000)
        salary_store.set_month_moc(self.conn, "2026-08", self.a, 8_200_000)
        self.assertEqual(self._row("2026-07")["monthly_salary"], 7_500_000)   # tháng 7 GIỮ số cũ
        self.assertEqual(self._row("2026-08")["monthly_salary"], 8_200_000)
        self.assertEqual(self._row("2026-09")["monthly_salary"], 8_200_000)   # kế thừa bản mới nhất

    def test_sua_thang_sau_khong_lam_doi_thang_truoc(self):
        salary_store.set_month_moc(self.conn, "2026-06", self.a, 6_800_000)
        salary_store.set_month_moc(self.conn, "2026-08", self.a, 9_000_000)
        self.assertEqual(self._row("2026-05")["monthly_salary"], 6_500_000)   # trước mọi bản → hồ sơ
        self.assertEqual(self._row("2026-06")["monthly_salary"], 6_800_000)
        self.assertEqual(self._row("2026-07")["monthly_salary"], 6_800_000)   # kế thừa tháng 6
        self.assertEqual(self._row("2026-08")["monthly_salary"], 9_000_000)

    def test_bo_moc_rieng_thang_nay_thi_ke_thua_lai(self):
        salary_store.set_month_moc(self.conn, "2026-07", self.a, 7_500_000)
        salary_store.set_month_moc(self.conn, "2026-08", self.a, 8_200_000)
        salary_store.set_month_moc(self.conn, "2026-08", self.a, 0)           # 0 = bỏ mốc riêng
        r8 = self._row("2026-08")
        self.assertEqual(r8["monthly_salary"], 7_500_000)
        self.assertEqual(r8["moc_ym"], "2026-07")
        self.assertFalse(r8["moc_own"])
        # bỏ luôn mốc tháng 7 → về mốc hồ sơ thợ
        salary_store.set_month_moc(self.conn, "2026-07", self.a, None)
        self.assertEqual(self._row("2026-08")["monthly_salary"], 6_500_000)
        self.assertEqual(self._row("2026-08")["moc_ym"], "")

    def test_moc_khong_de_len_thuong_ghi_chu_luong_tuan_cua_thang(self):
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, thuong=120_000,
                                     note="ghi chú tháng", weekly=True)
        salary_store.set_month_moc(self.conn, "2026-07", self.a, 7_500_000)
        r = self._row("2026-07")
        self.assertEqual(r["thuong"], 120_000)
        self.assertEqual(r["note"], "ghi chú tháng")
        self.assertTrue(r["weekly"])
        self.assertEqual(r["monthly_salary"], 7_500_000)
        # và ngược lại: sửa thưởng sau đó KHÔNG xoá mốc
        salary_store.set_month_adjust(self.conn, "2026-07", self.a, thuong=0)
        self.assertEqual(self._row("2026-07")["monthly_salary"], 7_500_000)

    # ── tiền thật sự tính theo mốc của tháng ────────────────────────────────────

    def test_luong_cong_tinh_theo_moc_cua_dung_thang_do(self):
        self._cham_cong("2026-07-06")          # 1 công tháng 7
        self._cham_cong("2026-08-06")          # 1 công tháng 8
        salary_store.set_month_moc(self.conn, "2026-07", self.a, 5_200_000)
        salary_store.set_month_moc(self.conn, "2026-08", self.a, 7_800_000)
        r7, r8 = self._row("2026-07"), self._row("2026-08")
        self.assertEqual(r7["cong"], 1.0)
        self.assertEqual(r7["luong_cong"], 200_000)   # 5,2tr/26 × 1 công
        self.assertEqual(r7["luong"], 200_000)
        self.assertEqual(r8["luong_cong"], 300_000)   # 7,8tr/26 × 1 công
        # sửa mốc tháng 8 KHÔNG đổi tiền tháng 7
        salary_store.set_month_moc(self.conn, "2026-08", self.a, 10_400_000)
        self.assertEqual(self._row("2026-07")["luong_cong"], 200_000)
        self.assertEqual(self._row("2026-08")["luong_cong"], 400_000)

    def test_lich_su_moc_cua_tho(self):
        salary_store.set_month_moc(self.conn, "2026-08", self.a, 8_200_000, by="trang")
        salary_store.set_month_moc(self.conn, "2026-06", self.a, 6_800_000, by="duy")
        hist = salary_store.list_worker_moc(self.conn, self.a)
        self.assertEqual([(h["ym"], h["value"]) for h in hist],
                         [("2026-06", 6_800_000), ("2026-08", 8_200_000)])   # tháng tăng dần
        self.assertEqual(hist[0]["by"], "duy")
        self.assertEqual(hist[1]["by"], "trang")
        # bỏ mốc → rơi khỏi lịch sử
        salary_store.set_month_moc(self.conn, "2026-06", self.a, 0)
        self.assertEqual([h["ym"] for h in salary_store.list_worker_moc(self.conn, self.a)], ["2026-08"])


if __name__ == "__main__":
    unittest.main()
