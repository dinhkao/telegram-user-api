import json
import sqlite3

from server_app.order_history import _get_order_history_rows


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE audit_events (
        id INTEGER PRIMARY KEY, ts TEXT, actor_id TEXT, actor_type TEXT,
        action TEXT, source TEXT, scope TEXT, thread_id INTEGER,
        payload_json TEXT, result_json TEXT
    )""")
    return conn


def _add(conn, *, action="http.request", source="", scope="order", payload=None, row_id=1):
    conn.execute(
        "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (row_id, f"2026-07-12T12:00:0{row_id}Z", "alice", "web_user", action,
         source, scope, 99, json.dumps(payload or {}), json.dumps({"status": 200})),
    )


def test_history_keeps_new_and_non_post_order_actions():
    conn = _conn()
    _add(conn, row_id=1, source="POST /api/order/99/custom-task",
         payload={"body": json.dumps({"label": "Gọi khách"})})
    _add(conn, row_id=2, source="DELETE /api/order/99")
    _add(conn, row_id=3, action="order.stock_allocated", source="inventory",
         payload={"boxes": [{"box_code": "K10-001", "taken": 20}]})

    rows = _get_order_history_rows(conn, 99, 20)

    assert [r["action"] for r in rows] == ["Xuất kho cho đơn", "Xóa đơn", "Thêm việc tùy chỉnh"]
    assert rows[0]["detail"] == "K10-001: 20"
    assert rows[2]["detail"] == "Gọi khách"


def test_history_shows_legacy_order_events_but_excludes_reads_and_other_scopes():
    conn = _conn()
    _add(conn, row_id=1, action="order.created", source="order.created", scope=None)
    _add(conn, row_id=2, source="GET /api/order/99")
    _add(conn, row_id=3, source="POST /api/order/preview")
    _add(conn, row_id=4, action="box.updated", source="box", scope="box")

    rows = _get_order_history_rows(conn, 99, 20)

    assert [r["action"] for r in rows] == ["Tạo đơn"]

