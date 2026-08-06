"""Test cấu hình BẢNG CHẤT LƯỢNG MÂM KẸO — chọn thợ nào hiện + thứ tự ô (lưới 2 cột).

Chỉ vài thợ sửa kẹo nên bảng #/chat-luong lọc theo settings_store
['quality_board_workers']. Logic thuần ở quality_store.domain (clean_board_ids /
select_board_rows) — cấu hình là JSON tự do nên phải chịu được dữ liệu rác.
"""
from __future__ import annotations

import unittest

from quality_store import domain


def _rows(*ids):
    return [{"id": i, "name": f"Tho {i}"} for i in ids]


class CleanBoardIdsTest(unittest.TestCase):
    def test_giu_nguyen_thu_tu_nguoi_dung_sap(self):
        # thứ tự CHÍNH LÀ vị trí ô — không được sort lại
        self.assertEqual(domain.clean_board_ids([5, 2, 9]), [5, 2, 9])

    def test_bo_trung_giu_lan_xuat_hien_dau(self):
        self.assertEqual(domain.clean_board_ids([3, 1, 3, 1, 7]), [3, 1, 7])

    def test_chuoi_so_van_nhan(self):
        self.assertEqual(domain.clean_board_ids(["4", 5]), [4, 5])

    def test_bo_gia_tri_rac(self):
        self.assertEqual(domain.clean_board_ids([1, None, "abc", {}, [], 2.9, 3]), [1, 2, 3])

    def test_bool_khong_bi_coi_la_id(self):
        # True/False lọt qua int() thành 1/0 → phải chặn, nếu không bảng hiện nhầm thợ id=1
        self.assertEqual(domain.clean_board_ids([True, False, 2]), [2])

    def test_khong_phai_list_thi_coi_nhu_chua_cau_hinh(self):
        for bad in (None, "", 0, {}, "1,2,3", 5):
            self.assertEqual(domain.clean_board_ids(bad), [])

    def test_loc_tho_da_xoa_khi_co_valid_ids(self):
        self.assertEqual(domain.clean_board_ids([1, 99, 2], valid_ids={1, 2, 3}), [1, 2])

    def test_valid_ids_rong_thi_khong_con_ai(self):
        self.assertEqual(domain.clean_board_ids([1, 2], valid_ids=set()), [])


class SelectBoardRowsTest(unittest.TestCase):
    def test_chua_cau_hinh_thi_hien_tat_ca(self):
        rows = _rows(1, 2, 3)
        self.assertEqual(domain.select_board_rows(rows, []), rows)

    def test_loc_va_sap_dung_thu_tu_cau_hinh(self):
        rows = _rows(1, 2, 3, 4)
        got = domain.select_board_rows(rows, [4, 1])
        self.assertEqual([r["id"] for r in got], [4, 1])

    def test_id_khong_con_tho_thi_bo_qua_khong_loi(self):
        rows = _rows(1, 2)
        got = domain.select_board_rows(rows, [2, 77, 1])
        self.assertEqual([r["id"] for r in got], [2, 1])

    def test_khong_sua_list_goc(self):
        rows = _rows(1, 2)
        out = domain.select_board_rows(rows, [])
        out.append({"id": 99, "name": "x"})
        self.assertEqual(len(rows), 2)

    def test_dem_da_chup_tinh_tren_tho_DANG_HIEN(self):
        # bảng chỉ hiện thợ 1 và 3 → "hôm nay x/y" không được tính thợ 2 (bị ẩn)
        rows = [
            {"id": 1, "today": {"reported": True}},
            {"id": 2, "today": {"reported": True}},
            {"id": 3, "today": {"reported": False}},
        ]
        shown = domain.select_board_rows(rows, [1, 3])
        done = sum(1 for r in shown if r["today"]["reported"])
        self.assertEqual((done, len(shown)), (1, 2))


if __name__ == "__main__":
    unittest.main()
