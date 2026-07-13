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
         payload={"boxes": [{"box_id": 7, "box_code": "K10-001", "product_code": "KDX30",
                             "taken": 20, "remaining": 5, "unit": "cây"}]})

    rows = _get_order_history_rows(conn, 99, 20)

    assert [r["action"] for r in rows] == ["Xuất kho cho đơn", "Xóa đơn", "Thêm việc tùy chỉnh"]
    # chi tiết ĐỌC ĐƯỢC: SP + số lượng + đơn vị + thùng + tồn còn, kèm link thùng/SP
    assert rows[0]["detail"] == "lấy 20 cây KDX30 từ thùng 001 (thùng còn 5)"
    hrefs = [p.get("href") for p in rows[0]["parts"] if p.get("href")]
    assert "#/thung/7" in hrefs and "#/kho/KDX30" in hrefs
    assert rows[2]["detail"] == "Gọi khách"


def test_history_shows_legacy_order_events_but_excludes_reads_and_other_scopes():
    conn = _conn()
    _add(conn, row_id=1, action="order.created", source="order.created", scope=None)
    _add(conn, row_id=2, source="GET /api/order/99")
    _add(conn, row_id=3, source="POST /api/order/preview")
    _add(conn, row_id=4, action="box.updated", source="box", scope="box")
    _add(conn, row_id=5, source="POST /api/order/99/stock-pick/lock")

    rows = _get_order_history_rows(conn, 99, 20)

    assert [r["action"] for r in rows] == ["Tạo đơn"]


def test_history_deduplicates_http_when_business_event_exists():
    conn = _conn()
    _add(conn, row_id=1, source="POST /api/order/99/allocate")
    _add(conn, row_id=2, action="order.stock_allocated", source="inventory",
         payload={"boxes": [{"box_code": "K10-001", "taken": 12}]})

    rows = _get_order_history_rows(conn, 99, 20)

    assert len(rows) == 1
    assert rows[0]["action"] == "Xuất kho cho đơn"


def test_read_requests_cannot_push_real_actions_out_of_query_window():
    conn = _conn()
    _add(conn, row_id=1, source="POST /api/order/task",
         payload={"body": json.dumps({"type": "giao_hang", "done": True})})
    for row_id in range(2, 352):
        _add(conn, row_id=row_id, source="GET /api/order/99/history")

    rows = _get_order_history_rows(conn, 99, 20)

    assert len(rows) == 1
    assert rows[0]["action"] == "Công việc"
