"""Dịch SQL phương ngữ SQLite -> PostgreSQL (thuần, không IO — unit-test được).

Dùng bởi utils.pg khi DB_ENGINE=postgres. Chỉ xử construct THẬT SỰ xuất hiện trong
repo (đã kiểm kê): placeholder `?`, `INSERT OR IGNORE`, `BEGIN IMMEDIATE`,
`datetime('now')`. Các hàm json_extract/json_set/json KHÔNG dịch ở đây — chúng được
tạo làm SQL function trong Postgres (migrations/pg/0001_init.sql) nên tên gọi giữ y
nguyên.

Giới hạn đã biết: giả định SQL string không chứa `?` hay `%` trong string literal
(đúng với repo — placeholder ở param, LIKE `%` nằm trong param). Nếu sau này thêm SQL
có literal như vậy, mở rộng ở đây + test.
"""
from __future__ import annotations

import re

_INSERT_IGNORE = re.compile(r"^(\s*)INSERT\s+OR\s+IGNORE\s+INTO", re.IGNORECASE)
_INSERT_REPLACE = re.compile(r"^(\s*)INSERT\s+OR\s+REPLACE\s+INTO", re.IGNORECASE)
_BEGIN_IMMEDIATE = re.compile(r"\bBEGIN\s+IMMEDIATE\b", re.IGNORECASE)


def translate(sql: str) -> str:
    """SQLite SQL -> Postgres SQL. Idempotent-ish cho các câu đã hợp lệ PG."""
    s = sql
    if _INSERT_IGNORE.search(s):
        s = _INSERT_IGNORE.sub(r"\1INSERT INTO", s)
        s = s.rstrip().rstrip(";")
        s = s + " ON CONFLICT DO NOTHING"
    elif _INSERT_REPLACE.search(s):
        # Không xuất hiện trong repo; để an toàn chuyển thành INSERT thường.
        s = _INSERT_REPLACE.sub(r"\1INSERT INTO", s)
    s = _BEGIN_IMMEDIATE.sub("BEGIN", s)
    s = s.replace("datetime('now')", "sqlite_datetime_now()")
    # qmark -> pyformat (escape % literal trước, rồi ? -> %s)
    s = s.replace("%", "%%").replace("?", "%s")
    return s
