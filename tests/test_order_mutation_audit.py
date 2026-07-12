import json
import sqlite3

from order_store.mutation_audit import reset_actor, set_actor
from order_store.serialization import _save_order


def _conn():
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE orders (thread_id INTEGER PRIMARY KEY, json TEXT, updated_at INTEGER, deleted_at INTEGER)")
    conn.execute("""CREATE TABLE audit_events (
        id INTEGER PRIMARY KEY, ts TEXT, request_id TEXT, actor_type TEXT,
        actor_id TEXT, action TEXT, source TEXT, scope TEXT,
        thread_id INTEGER, payload_json TEXT
    )""")
    conn.execute("INSERT INTO orders VALUES (7, ?, 1, NULL)", (json.dumps({"vat": 0}),))
    return conn


def test_non_http_save_is_audited_at_order_store_choke_point():
    conn = _conn()

    assert _save_order(conn, 7, {"vat": 8000})

    row = conn.execute("SELECT * FROM audit_events").fetchone()
    assert row["action"] == "order.changed"
    assert row["scope"] == "order"
    assert row["thread_id"] == 7
    assert json.loads(row["payload_json"])["changes"][0]["label"] == "VAT"


def test_http_save_is_left_to_request_audit_to_avoid_duplicate_rows():
    conn = _conn()
    token = set_actor("web_user", "duy")
    try:
        assert _save_order(conn, 7, {"vat": 8000})
    finally:
        reset_actor(token)

    assert conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 0
