"""Test nội dung THÔNG BÁO phiếu kho đậu (server_app.bean_notify.build_bean_notif):
tiêu đề theo loại phiếu, dòng nhập/xuất nói theo ĐƠN VỊ NGƯỜI GÕ, dòng điều chỉnh
nói số đếm + chênh lệch theo ĐƠN VỊ GỐC, và route deep-link tới phiếu."""
from __future__ import annotations

import unittest

from server_app.bean_notify import build_bean_notif


def _slip(kind, items, **kw):
    base = {"id": 12, "kind": kind, "place_name": "Kho A", "items": items}
    base.update(kw)
    return base


def _item(name, qty, *, unit="kg", entered=None, entered_unit="", delta=0.0):
    return {"bean_name": name, "quantity": qty, "unit": unit, "delta": delta,
            "entered_qty": qty if entered is None else entered,
            "unit_name": entered_unit, "entered_unit": entered_unit or unit}


class BeanNotifTest(unittest.TestCase):
    def test_nhap_theo_don_vi_nguoi_go(self):
        # gõ 3 bao (= 150 kg) → thông báo nói "3 bao", không phải 150
        it = _item("Đậu xanh", 150.0, entered=3, entered_unit="bao", delta=150.0)
        title, body, data = build_bean_notif(_slip("nhap", [it]), "duy")
        self.assertIn("Nhập kho đậu", title)
        self.assertIn("Đậu xanh 3 bao", body)
        self.assertIn("duy", body)
        self.assertIn("Kho A", body)
        self.assertEqual(data["route"], "#/kho-dau/phieu/12")
        self.assertEqual(data["type"], "bean_slip")

    def test_xuat_va_partner(self):
        it = _item("Đậu phộng", 20.5, delta=-20.5)
        title, body, _ = build_bean_notif(_slip("xuat", [it], partner="Xưởng 2"), "an")
        self.assertIn("Xuất kho đậu", title)
        self.assertIn("Đậu phộng 20,5 kg", body)   # dấu thập phân kiểu Việt
        self.assertIn("(Xưởng 2)", body)

    def test_dieu_chinh_hien_chenh_lech_theo_don_vi_goc(self):
        it = _item("Đậu xanh", 48.0, delta=-2.0)
        title, body, _ = build_bean_notif(_slip("dieu_chinh", [it]), "duy")
        self.assertIn("Điều chỉnh kho đậu", title)
        self.assertIn("Đậu xanh 48 kg", body)
        self.assertIn("−2 kg", body)

    def test_dieu_chinh_khong_doi(self):
        _, body, _ = build_bean_notif(_slip("dieu_chinh", [_item("Đậu xanh", 10.0)]), "duy")
        self.assertIn("không đổi", body)

    def test_phieu_dai_bi_cat_bot(self):
        items = [_item(f"Đậu {i}", i + 1.0, delta=i + 1.0) for i in range(6)]
        _, body, _ = build_bean_notif(_slip("nhap", items), "duy")
        self.assertIn("+3 dòng nữa", body)
        self.assertNotIn("Đậu 4", body)
        self.assertLessEqual(len(body), 200)

    def test_thieu_actor_van_ra_body(self):
        _, body, _ = build_bean_notif(_slip("nhap", [_item("Đậu xanh", 5.0, delta=5.0)]), "")
        self.assertIn("Kho A: Đậu xanh 5 kg", body)


if __name__ == "__main__":
    unittest.main()
