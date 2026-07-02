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


if __name__ == "__main__":
    unittest.main()
