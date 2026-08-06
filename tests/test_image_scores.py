"""Test entity_media_store.scores (CHẤM ĐIỂM 0–10 mỗi ảnh — RIÊNG TỪNG NGƯỜI) +
comment_counts: parse_score chặn số xấu/ngoài thang, mỗi user giữ điểm của mình,
clear chỉ bỏ điểm của chính mình, scores_for theo lô (kèm my_score), avg_by_entity
gộp 2 tầng (trung bình từng ảnh rồi mới theo thực thể)."""
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
    def test_moi_nguoi_mot_diem_rieng(self):
        scores.set_score("area_report", self.img1, 7, "duy", db_path=self.path)
        got = scores.scores_for("area_report", [self.img1], "duy", db_path=self.path)
        self.assertEqual(got[self.img1]["score"], 7.0)
        self.assertEqual(got[self.img1]["score_count"], 1)
        self.assertEqual(got[self.img1]["my_score"], 7)

        # người KHÁC chấm: KHÔNG đè điểm của duy, ảnh thành 2 điểm → TB (7+9)/2
        scores.set_score("area_report", self.img1, 9, "tho", db_path=self.path)
        got = scores.scores_for("area_report", [self.img1], "duy", db_path=self.path)
        self.assertEqual(got[self.img1]["score"], 8.0)
        self.assertEqual(got[self.img1]["score_count"], 2)
        self.assertEqual(got[self.img1]["my_score"], 7)          # điểm của duy giữ nguyên
        self.assertEqual({r["by"]: r["score"] for r in got[self.img1]["raters"]},
                         {"duy": 7, "tho": 9})

        # chấm lại = ghi đè điểm CỦA CHÍNH MÌNH
        scores.set_score("area_report", self.img1, 3, "duy", db_path=self.path)
        got = scores.scores_for("area_report", [self.img1], "duy", db_path=self.path)
        self.assertEqual(got[self.img1]["my_score"], 3)
        self.assertEqual(got[self.img1]["score_count"], 2)       # vẫn 2 người
        self.assertEqual(got[self.img1]["score"], 6.0)           # (3+9)/2

    def test_my_score_theo_dung_nguoi_xem(self):
        scores.set_score("area_report", self.img1, 7, "duy", db_path=self.path)
        scores.set_score("area_report", self.img1, 9, "tho", db_path=self.path)
        self.assertEqual(scores.scores_for("area_report", [self.img1], "tho",
                                           db_path=self.path)[self.img1]["my_score"], 9)
        # người chưa chấm / không truyền viewer → my_score = None
        self.assertIsNone(scores.scores_for("area_report", [self.img1], "ai_do",
                                            db_path=self.path)[self.img1]["my_score"])
        self.assertIsNone(scores.scores_for("area_report", [self.img1],
                                            db_path=self.path)[self.img1]["my_score"])

    def test_clear_chi_bo_diem_cua_minh(self):
        scores.set_score("area_report", self.img1, 7, "duy", db_path=self.path)
        scores.set_score("area_report", self.img1, 9, "tho", db_path=self.path)
        self.assertTrue(scores.clear_score("area_report", self.img1, "duy", db_path=self.path))
        got = scores.scores_for("area_report", [self.img1], "duy", db_path=self.path)
        self.assertIsNone(got[self.img1]["my_score"])
        self.assertEqual(got[self.img1]["score"], 9.0)           # điểm của tho còn nguyên
        self.assertEqual(got[self.img1]["score_count"], 1)
        # bỏ lần hai: không còn gì để bỏ
        self.assertFalse(scores.clear_score("area_report", self.img1, "duy", db_path=self.path))
        # by=None = dọn sạch (dùng khi xoá hẳn ảnh)
        self.assertTrue(scores.clear_score("area_report", self.img1, db_path=self.path))
        self.assertEqual(scores.scores_for("area_report", [self.img1], db_path=self.path), {})

    def test_migration_tu_bang_cu_1_anh_1_diem(self):
        """Bảng cũ khoá (scope,image_id) → nâng lên (scope,image_id,scored_by),
        dữ liệu cũ thành điểm của chính người đã chấm."""
        import sqlite3
        from entity_media_store import scores as sc
        c = sqlite3.connect(self.path)
        c.execute("DROP TABLE IF EXISTS entity_image_scores")
        c.execute("CREATE TABLE entity_image_scores (scope TEXT NOT NULL, image_id INTEGER NOT NULL,"
                  " score INTEGER NOT NULL, scored_by TEXT NOT NULL DEFAULT '?',"
                  " scored_at INTEGER NOT NULL, PRIMARY KEY (scope, image_id))")
        c.execute("INSERT INTO entity_image_scores VALUES ('area_report', ?, 6, 'duy', 111)", (self.img1,))
        c.execute("INSERT INTO entity_image_scores VALUES ('area_report', ?, 4, '', 222)", (self.img2,))
        c.commit(); c.close()
        sc._ensured.discard(self.path)          # ép chạy lại bước ensure/migrate

        got = scores.scores_for("area_report", [self.img1, self.img2], "duy", db_path=self.path)
        self.assertEqual(got[self.img1]["my_score"], 6)          # giữ đúng chủ điểm cũ
        self.assertEqual(got[self.img2]["score"], 4.0)
        self.assertEqual(got[self.img2]["raters"][0]["by"], "?")  # scored_by rỗng → '?'
        # sau khi nâng cấp, người khác chấm thêm được (không còn bị đè)
        scores.set_score("area_report", self.img1, 10, "tho", db_path=self.path)
        got = scores.scores_for("area_report", [self.img1], "duy", db_path=self.path)
        self.assertEqual(got[self.img1]["score_count"], 2)
        self.assertEqual(got[self.img1]["score"], 8.0)

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
        scores.clear_score("area_report", self.img2, "duy", db_path=self.path)
        avg = scores.avg_by_entity("area_report", [5], db_path=self.path)
        self.assertEqual(avg[5], {"avg": 8.0, "count": 1})

    def test_avg_2_tang_anh_nhieu_nguoi_cham_khong_nang_hon(self):
        """1 ảnh 3 người chấm KHÔNG được tính nặng gấp 3 ảnh 1 người chấm:
        lấy TB của từng ảnh trước, rồi mới TB theo báo cáo."""
        for who, n in (("a", 10), ("b", 10), ("c", 10)):
            scores.set_score("area_report", self.img1, n, who, db_path=self.path)
        scores.set_score("area_report", self.img2, 0, "a", db_path=self.path)
        avg = scores.avg_by_entity("area_report", [5], db_path=self.path)
        # đúng: (10 + 0)/2 = 5.0 — nếu gộp phẳng 4 dòng sẽ ra 7.5
        self.assertEqual(avg[5], {"avg": 5.0, "count": 2})

    def test_score_scoped_per_scope(self):
        """Điểm khoá theo (scope, image_id, người) — scope khác không thấy điểm của nhau."""
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
