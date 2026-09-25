"""Icon ⏺ đang xuất kho trên card dashboard (server_app/order_stock_picking)."""
import sqlite3

from server_app.order_stock_picking import apply_picking_icon, attach_stock_picking


def test_apply_only_replaces_pending_soan():
    assert apply_picking_icon("✅❌❌❌❌😡", True) == "✅⏺❌❌❌😡"
    assert apply_picking_icon("✅❌❌❌❌😡", False) == "✅❌❌❌❌😡"
    assert apply_picking_icon("✅📦❌❌❌😡", True) == "✅📦❌❌❌😡"   # đã chốt kho
    assert apply_picking_icon("✅✅❌❌❌😡", True) == "✅✅❌❌❌😡"   # đã soạn
    assert apply_picking_icon("", True) == ""


def test_attach_uses_order_allocations_only():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE box_allocations (box_id INT, order_thread_id INT, quantity REAL, kind TEXT)")
    conn.executemany("INSERT INTO box_allocations VALUES (?,?,?,?)",
                     [(1, 10, 5, "order"), (1, 11, 5, None), (2, 12, 5, "production")])
    orders = [{"thread_id": t, "task_icons": "✅❌❌❌❌😡"} for t in (10, 11, 12, 13)]
    attach_stock_picking(conn, orders)
    assert [o["task_icons"][1] for o in orders] == ["⏺", "⏺", "❌", "❌"]


def test_attach_without_table_is_noop():
    conn = sqlite3.connect(":memory:")
    orders = [{"thread_id": 1, "task_icons": "✅❌❌❌❌😡"}]
    attach_stock_picking(conn, orders)
    assert orders[0]["task_icons"] == "✅❌❌❌❌😡"
