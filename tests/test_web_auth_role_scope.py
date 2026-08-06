"""Test hàng rào PHẠM VI API của vai trò `chat_luong` (chỉ trang chất lượng mâm kẹo).

Đây là chặn THẬT ở middleware — không phải ẩn menu. Nguyên tắc: MẶC ĐỊNH TỪ CHỐI,
chỉ mở đúng /api/auth*, /api/quality*, và /api/media/{quality_report,quality_image}*.
"""
from __future__ import annotations

import unittest

from server_app.web_auth.role_scope import (QUALITY_ONLY_ROLE, allowed_for_quality_only,
                                            api_scope_denied)


class QualityOnlyScopeTest(unittest.TestCase):
    def test_duong_cua_trang_chat_luong_deu_qua(self):
        for m, p in [
            ("GET", "/api/quality"),
            ("GET", "/api/quality/7"),
            ("POST", "/api/quality/7/report"),
            ("GET", "/api/media/quality_report/12/images"),
            ("POST", "/api/media/quality_report/12/images"),
            ("GET", "/api/media/quality_report/12/images/5/file"),
            ("POST", "/api/media/quality_report/12/images/5/score"),
            ("DELETE", "/api/media/quality_report/12/images/5/score"),
            ("GET", "/api/media/quality_report/12/comments"),
            ("POST", "/api/media/quality_image/5/comments"),
            ("GET", "/api/auth/me"),
            ("POST", "/api/auth/login"),
        ]:
            self.assertTrue(allowed_for_quality_only(m, p), f"{m} {p} phải được phép")

    def test_moi_thu_khac_bi_chan(self):
        for m, p in [
            ("GET", "/api/orders"),
            ("GET", "/api/order/123"),
            ("POST", "/api/order/123/payment"),
            ("GET", "/api/customers"),
            ("GET", "/api/kho"),
            ("GET", "/api/workers"),
            ("GET", "/api/users"),
            ("POST", "/api/settings"),
            ("GET", "/api/payroll"),
            ("GET", "/api/wages"),
            ("GET", "/api/areas"),                       # trang vệ sinh: KHÔNG thuộc phạm vi
            ("GET", "/api/media/area_report/3/images"),  # ảnh vệ sinh: KHÔNG
            ("POST", "/api/media/order/3/images"),       # ảnh đơn hàng: KHÔNG
        ]:
            self.assertFalse(allowed_for_quality_only(m, p), f"{m} {p} phải bị chặn")

    def test_khong_lot_bang_tien_to_gan_giong(self):
        # Chốt chặn: so khớp phải theo TỪNG ĐOẠN, không phải startswith
        for p in [
            "/api/quality-secret",
            "/api/qualityx/1",
            "/api/authx/hack",
            "/api/media/quality_report_x/1/images",
            "/api/media/quality_reportevil/1",
            "/api/media/xquality_image/1/comments",
        ]:
            self.assertFalse(allowed_for_quality_only("GET", p), f"{p} phải bị chặn")

    def test_duong_ngoai_api_khong_dung_toi(self):
        # trang tĩnh + /ws gate ở chỗ khác, middleware này không chặn
        for p in ["/", "/index.html", "/assets/app.js", "/ws"]:
            self.assertTrue(allowed_for_quality_only("GET", p))

    def test_options_luon_qua(self):
        self.assertTrue(allowed_for_quality_only("OPTIONS", "/api/orders"))
        self.assertTrue(allowed_for_quality_only("options", "/api/orders"))

    def test_duong_di_ky_la_thi_tu_choi(self):
        self.assertFalse(allowed_for_quality_only("GET", "/api/"))
        self.assertFalse(allowed_for_quality_only("GET", "/api//"))


class ApiScopeDeniedTest(unittest.TestCase):
    def test_chi_vai_tro_chat_luong_bi_bo_hep(self):
        for role in ("admin", "van_phong", "staff", "", None):
            self.assertFalse(api_scope_denied(role, "GET", "/api/orders"),
                             f"role {role!r} không được bị chặn")

    def test_chat_luong_bi_chan_ngoai_pham_vi(self):
        self.assertTrue(api_scope_denied(QUALITY_ONLY_ROLE, "GET", "/api/orders"))
        self.assertTrue(api_scope_denied(QUALITY_ONLY_ROLE, "GET", "/api/media/area_report/1/images"))

    def test_chat_luong_qua_duoc_trong_pham_vi(self):
        self.assertFalse(api_scope_denied(QUALITY_ONLY_ROLE, "GET", "/api/quality"))
        self.assertFalse(api_scope_denied(QUALITY_ONLY_ROLE, "POST", "/api/quality/3/report"))

    def test_vai_tro_nam_trong_danh_sach_ROLES(self):
        from user_store.users import ROLES, OFFICE_ROLES, is_office, is_quality_only
        self.assertIn(QUALITY_ONLY_ROLE, ROLES)
        # KHÔNG được là văn phòng, nếu không sẽ mở toang các gate office sẵn có
        self.assertNotIn(QUALITY_ONLY_ROLE, OFFICE_ROLES)
        self.assertFalse(is_office(QUALITY_ONLY_ROLE))
        self.assertTrue(is_quality_only(QUALITY_ONLY_ROLE))


if __name__ == "__main__":
    unittest.main()
