"""Unit tests comment_store — bảng web_comments trên SQLite tạm (không đụng app.db)."""
from __future__ import annotations

import os
import tempfile
import unittest

from comment_store import add_comment, list_comments


class CommentStore(unittest.TestCase):
    def setUp(self):
        self.db = os.path.join(tempfile.mkdtemp(), "test.db")

    def test_add_and_list(self):
        add_comment(101, "duy", "giao trước 5h", db_path=self.db)
        add_comment(101, "trang", "ok đã soạn", db_path=self.db)
        add_comment(202, "duy", "đơn khác", db_path=self.db)
        comments = list_comments(101, db_path=self.db)
        self.assertEqual([c["username"] for c in comments], ["duy", "trang"])
        self.assertEqual(comments[0]["text"], "giao trước 5h")
        self.assertEqual(len(list_comments(202, db_path=self.db)), 1)

    def test_empty_text_rejected(self):
        with self.assertRaises(ValueError):
            add_comment(101, "duy", "   ", db_path=self.db)

    def test_empty_thread(self):
        self.assertEqual(list_comments(999, db_path=self.db), [])

    def test_returned_shape(self):
        c = add_comment(5, "duy", "note", db_path=self.db)
        self.assertEqual(c["thread_id"], 5)
        self.assertIn("id", c)
        self.assertIn("created_at", c)

    def test_topic_same_thread_unknown_topic_is_general(self):
        add_comment(7, "duy", "chung", db_path=self.db)
        add_comment(7, "duy", "sửa giá", topic="hoa_don", db_path=self.db)
        add_comment(7, "duy", "lạ", topic="bậy", db_path=self.db)
        cs = list_comments(7, db_path=self.db)   # 1 luồng chung, đủ cả 3
        self.assertEqual([c["topic"] for c in cs], [None, "hoa_don", None])

    def test_old_table_without_topic_is_migrated(self):
        import sqlite3
        from comment_store import comments as mod
        c = sqlite3.connect(self.db)
        c.execute("CREATE TABLE web_comments (id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id INTEGER NOT NULL,"
                  " username TEXT NOT NULL, text TEXT NOT NULL, created_at INTEGER NOT NULL)")
        c.execute("INSERT INTO web_comments (thread_id, username, text, created_at) VALUES (1, 'a', 'cũ', 1)")
        c.commit(); c.close()
        mod._ensured.discard(self.db)
        add_comment(1, "b", "mới", topic="giao_hang", db_path=self.db)
        self.assertEqual([x["topic"] for x in list_comments(1, db_path=self.db)], [None, "giao_hang"])


if __name__ == "__main__":
    unittest.main()
