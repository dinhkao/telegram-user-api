"""Unit test bộ dịch SQL SQLite->Postgres (utils.sql_translate). Không cần PG."""
from utils.sql_translate import translate


def test_qmark_to_pyformat():
    assert translate("SELECT * FROM orders WHERE thread_id = ?") == \
        "SELECT * FROM orders WHERE thread_id = %s"


def test_multiple_placeholders():
    assert translate("INSERT INTO t(a,b) VALUES (?, ?)") == \
        "INSERT INTO t(a,b) VALUES (%s, %s)"


def test_insert_or_ignore():
    out = translate("INSERT OR IGNORE INTO orders(firebase_key, thread_id) VALUES (?, ?)")
    assert out == "INSERT INTO orders(firebase_key, thread_id) VALUES (%s, %s) ON CONFLICT DO NOTHING"


def test_insert_or_ignore_strips_trailing_semicolon():
    out = translate("INSERT OR IGNORE INTO t(a) VALUES (?);")
    assert out == "INSERT INTO t(a) VALUES (%s) ON CONFLICT DO NOTHING"


def test_begin_immediate():
    assert translate("BEGIN IMMEDIATE") == "BEGIN"


def test_datetime_now():
    assert translate("UPDATE t SET updated_at = datetime('now') WHERE id = ?") == \
        "UPDATE t SET updated_at = sqlite_datetime_now() WHERE id = %s"


def test_percent_literal_escaped():
    # % literal (nếu có trong SQL) phải thành %% cho psycopg pyformat
    assert translate("SELECT * FROM t WHERE x LIKE 'a%'") == \
        "SELECT * FROM t WHERE x LIKE 'a%%'"


def test_json_functions_untouched():
    # json_extract/json_set/json là SQL function phía PG — tên giữ nguyên
    sql = "SELECT json_extract(json, '$.created') FROM orders WHERE thread_id = ?"
    assert translate(sql) == "SELECT json_extract(json, '$.created') FROM orders WHERE thread_id = %s"


def test_json_set_untouched_names():
    sql = "UPDATE orders SET json = json_set(json, ?, json(?)) WHERE thread_id = ?"
    assert translate(sql) == \
        "UPDATE orders SET json = json_set(json, %s, json(%s)) WHERE thread_id = %s"
