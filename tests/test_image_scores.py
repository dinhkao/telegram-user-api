"""Test entity_media_store.scores (CHẤM ĐIỂM 0–10 mỗi ảnh) + comment_counts:
parse_score chặn số xấu/ngoài thang, set ghi đè, clear, scores_for theo lô,
avg_by_entity gộp theo thực thể (join entity_images)."""
from __future__ import annotations

import os
import tempfile
import unittest

from entity_media_store import add_comment, add_image, comment_counts
from entity_media_store import scores


class ImageScoreTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        # mỗi test 1 DB riêng → truyền db_path cho mọi call (store cache ensure theo path)
        self.img1 = add_image("area_report", 5, "a.webp", "a_t.webp", "image/webp",
                              uploaded_by="duy", db_path=self.path)["id"]
        self.img2 = add_image("area_report", 5, "b.webp", "b_t.webp", "image/webp",
                              uploaded_by="duy", db_path=self.path)["id"]
        self.img3 = add_image("area_report", 6, "c.webp", "c_t.webp", "image/webp",
                              uploaded_by="duy", db_path=self.path)["id"]

    def tearDown(self):
        os.unlink(self.path)

    # ── parse_score ──────────────────────────────────────────────────────────
    def test_parse_score_range(self):
        self.assertEqual(scores.parse_score(0), 0)
        self.assertEqual(scores.parse_score(10), 10)
        self.assertEqual(scores.parse_score("8"), 8)
        self.assertEqual(scores.parse_score(7.4), 7)     # làm tròn
        for bad in (-1, 11, "x", None, ""):
            with self.assertRaises(ValueError):
                scores.parse_score(bad)

    # ── set / clear / đọc ────────────────────────────────────────────────────
    def test_set_overwrite_and_clear(self):
        scores.set_score("area_report", self.img1, 7, "duy", db_path=self.path)
        got = scores.scores_for("area_report", [self.img1], db_path=self.path)
        self.assertEqual(got[self.img1]["score"], 7)
        self.assertEqual(got[self.img1]["scored_by"], "duy")

        # chấm lại = GHI ĐÈ (1 ảnh 1 điểm), đổi cả người chấm
        scores.set_score("area_report", self.img1, 9, "tho", db_path=self.path)
        got = scores.scores_for("area_report", [self.img1], db_path=self.path)
        self.assertEqual(got[self.img1]["score"], 9)
        self.assertEqual(got[self.img1]["scored_by"], "tho")

        self.assertTrue(scores.clear_score("area_report", self.img1, db_path=self.path))
        self.assertEqual(scores.scores_for("area_report", [self.img1], db_path=self.path), {})
        self.assertFalse(scores.clear_score("area_report", self.img1, db_path=self.path))

    def test_scores_for_empty(self):
        self.assertEqual(scores.scores_for("area_report", [], db_path=self.path), {})
        self.assertEqual(scores.avg_by_entity("area_report", [], db_path=self.path), {})

    # ── điểm trung bình theo thực thể (1 báo cáo = 1 ngày) ───────────────────
    def test_avg_by_entity(self):
        scores.set_score("area_report", self.img1, 8, "duy", db_path=self.path)
        scores.set_score("area_report", self.img2, 5, "duy", db_path=self.path)
        scores.set_score("area_report", self.img3, 10, "duy", db_path=self.path)
        avg = scores.avg_by_entity("area_report", [5, 6, 7], db_path=self.path)
        self.assertEqual(avg[5], {"avg": 6.5, "count": 2})
        self.assertEqual(avg[6], {"avg": 10.0, "count": 1})
        self.assertNotIn(7, avg)          # thực thể chưa có ảnh chấm → không có khoá

        # bỏ 1 điểm → TB tính lại theo phần còn lại
        scores.clear_score("area_report", self.img2, db_path=self.path)
        avg = scores.avg_by_entity("area_report", [5], db_path=self.path)
        self.assertEqual(avg[5], {"avg": 8.0, "count": 1})

    def test_score_scoped_per_scope(self):
        """Điểm khoá theo (scope, image_id) — scope khác không thấy điểm của nhau."""
        scores.set_score("area_report", self.img1, 8, "duy", db_path=self.path)
        self.assertEqual(scores.scores_for("quality_report", [self.img1], db_path=self.path), {})

    # ── đếm bình luận (badge 💬) ─────────────────────────────────────────────
    def test_comment_counts(self):
        add_comment("area_image", self.img1, "duy", "sạch", db_path=self.path)
        add_comment("area_image", self.img1, "tho", "ok", db_path=self.path)
        add_comment("area_image", self.img2, "duy", "còn bẩn", db_path=self.path)
        counts = comment_counts("area_image", [self.img1, self.img2, self.img3], db_path=self.path)
        self.assertEqual(counts.get(self.img1), 2)
        self.assertEqual(counts.get(self.img2), 1)
        self.assertNotIn(self.img3, counts)
        self.assertEqual(comment_counts("area_image", [], db_path=self.path), {})


if __name__ == "__main__":
    unittest.main()
