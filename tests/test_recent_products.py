"""Test entity_media_store.recent_products — MÃ SP gắn cho ảnh gần đây nhất của
1 scope (trang chất lượng mâm kẹo đẩy các mã này lên đầu danh sách chọn SP).
Luật: mới-dùng-trước, không trùng, bỏ ảnh không gắn SP, không lẫn scope khác,
và chỉ nhìn `scan` ảnh mới nhất."""
from __future__ import annotations

import os
import tempfile
import unittest

from entity_media_store import add_image, recent_products


class RecentProductsTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

    def tearDown(self):
        os.unlink(self.path)

    def _img(self, scope: str, product: str, entity_id: int = 1):
        return add_image(scope, entity_id, "a.webp", "a_t.webp", "image/webp",
                         uploaded_by="duy", product=product, db_path=self.path)

    def test_moi_dung_truoc_va_khong_trung(self):
        for code in ("K1", "K2", "K1", "K3"):
            self._img("quality_report", code)
        self.assertEqual(recent_products("quality_report", db_path=self.path),
                         ["K3", "K1", "K2"])

    def test_bo_anh_khong_gan_sp_va_scope_khac(self):
        self._img("quality_report", "")
        self._img("area_report", "KHU")
        self._img("quality_report", "K9")
        self.assertEqual(recent_products("quality_report", db_path=self.path), ["K9"])

    def test_limit_va_scan(self):
        for i in range(12):
            self._img("quality_report", f"K{i}")
        self.assertEqual(recent_products("quality_report", limit=3, db_path=self.path),
                         ["K11", "K10", "K9"])
        # scan=2 → chỉ nhìn 2 ảnh mới nhất, mã cũ hơn không còn coi là "gần đây"
        self.assertEqual(recent_products("quality_report", scan=2, db_path=self.path),
                         ["K11", "K10"])

    def test_khong_co_anh(self):
        self.assertEqual(recent_products("quality_report", db_path=self.path), [])


if __name__ == "__main__":
    unittest.main()
