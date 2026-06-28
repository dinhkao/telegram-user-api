"""bot_core/db_queries.py — Complex query functions for orders."""
import json
from datetime import datetime, timedelta, timezone


def get_orders_without_giao(conn, limit: int = 5) -> list[dict]:
    """Get last N orders without giao_hang completed."""
    rows = conn.execute(
        "SELECT json FROM orders WHERE deleted_at IS NULL "
        "AND thread_id IS NOT NULL "
        "AND thread_id < 1000000000 "
        "AND json_extract(json, '$.text') IS NOT NULL "
        "AND json_extract(json, '$.text') != '' "
        "AND lower(json_extract(json, '$.text')) NOT LIKE 'test%' "
        "AND (json_extract(json, '$.task_status.giao_hang.done') IS NULL "
        "     OR json_extract(json, '$.task_status.giao_hang.done') != 1) "
        "ORDER BY thread_id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [json.loads(r[0]) for r in rows if r]


def get_orders_without_giao_paginated(conn, page: int = 1, per_page: int = 10, days: int = 30):
    """Get orders without giao_hang, created in last N days. Returns (orders, total)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    base = (
        "FROM orders WHERE deleted_at IS NULL "
        "AND thread_id IS NOT NULL "
        "AND thread_id < 1000000000 "
        "AND json_extract(json, '$.text') IS NOT NULL "
        "AND json_extract(json, '$.text') != '' "
        "AND lower(json_extract(json, '$.text')) NOT LIKE 'test%' "
        "AND json_extract(json, '$.created') >= ? "
        "AND (json_extract(json, '$.task_status.giao_hang.done') IS NULL "
        "     OR json_extract(json, '$.task_status.giao_hang.done') != 1) "
    )
    total = conn.execute(f"SELECT COUNT(*) {base}", (cutoff,)).fetchone()[0]
    rows = conn.execute(
        f"SELECT json {base} ORDER BY thread_id DESC LIMIT ? OFFSET ?",
        (cutoff, per_page, (page - 1) * per_page),
    ).fetchall()
    return [json.loads(r[0]) for r in rows if r], total


def get_orders_without_nop(conn, page: int = 1, per_page: int = 10):
    """Orders where nop_tien OR nhan_tien NOT done, created after 2026-04-01."""
    base = (
        "FROM orders WHERE deleted_at IS NULL "
        "AND thread_id IS NOT NULL "
        "AND thread_id < 1000000000 "
        "AND json_extract(json, '$.text') IS NOT NULL "
        "AND json_extract(json, '$.text') != '' "
        "AND lower(json_extract(json, '$.text')) NOT LIKE 'test%' "
        "AND json_extract(json, '$.created') >= '2026-04-01' "
        "AND ("
        "     json_extract(json, '$.task_status.nop_tien.done') IS NULL "
        "     OR json_extract(json, '$.task_status.nop_tien.done') != 1 "
        "     OR json_extract(json, '$.task_status.nhan_tien.done') IS NULL "
        "     OR json_extract(json, '$.task_status.nhan_tien.done') != 1"
        ") "
    )
    total = conn.execute(f"SELECT COUNT(*) {base}").fetchone()[0]
    rows = conn.execute(
        f"SELECT json {base} ORDER BY thread_id DESC LIMIT ? OFFSET ?",
        (per_page, (page - 1) * per_page),
    ).fetchall()
    return [json.loads(r[0]) for r in rows if r], total


def search_orders(conn, keyword: str, page: int = 1, per_page: int = 10):
    """Search orders by keyword (accent-insensitive) created after 2026-04-01."""
    from bot_core.utils import _norm
    norm_kw = _norm(keyword)
    rows = conn.execute(
        "SELECT json FROM orders WHERE deleted_at IS NULL "
        "AND thread_id IS NOT NULL "
        "AND json_extract(json, '$.text') IS NOT NULL "
        "AND json_extract(json, '$.text') != '' "
        "AND json_extract(json, '$.created') >= '2026-04-01' "
        "ORDER BY thread_id DESC"
    ).fetchall()
    matched = []
    for r in rows:
        o = json.loads(r[0])
        text = o.get("text", "")
        if norm_kw in _norm(text):
            matched.append(o)
    total = len(matched)
    start = (page - 1) * per_page
    return matched[start:start + per_page], total
