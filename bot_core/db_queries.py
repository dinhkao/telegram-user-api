"""bot_core/db_queries.py — Complex query functions for orders."""
import json
from datetime import datetime, timedelta, timezone


def get_orders_without_giao(conn, limit: int = 5) -> list[dict]:
    rows = conn.execute(
        "SELECT json FROM orders WHERE deleted_at IS NULL "
        "AND thread_id IS NOT NULL AND thread_id < 1000000000 "
        "AND json_extract(json, '$.text') IS NOT NULL "
        "AND json_extract(json, '$.text') != '' "
        "AND lower(json_extract(json, '$.text')) NOT LIKE 'test%' "
        "AND (json_extract(json, '$.task_status.giao_hang.done') IS NULL "
        "     OR json_extract(json, '$.task_status.giao_hang.done') != 1) "
        "ORDER BY thread_id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [json.loads(r[0]) for r in rows if r]


def get_orders_without_giao_paginated(conn, page=1, per_page=10, days=30):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    base = (
        "FROM orders WHERE deleted_at IS NULL "
        "AND thread_id IS NOT NULL AND thread_id < 1000000000 "
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
        (cutoff, per_page, (page - 1) * per_page)
    ).fetchall()
    return [json.loads(r[0]) for r in rows if r], total


def get_orders_without_nop(conn, page=1, per_page=10):
    base = (
        "FROM orders WHERE deleted_at IS NULL "
        "AND thread_id IS NOT NULL AND thread_id < 1000000000 "
        "AND json_extract(json, '$.text') IS NOT NULL "
        "AND json_extract(json, '$.text') != '' "
        "AND lower(json_extract(json, '$.text')) NOT LIKE 'test%' "
        "AND order_created >= '2026-04-01' "
        "AND nop_nhan_done = 0 "
        "AND json_extract(json, '$.task_status.giao_hang.done') = 1 "
    )
    total = conn.execute(f"SELECT COUNT(*) {base}").fetchone()[0]
    rows = conn.execute(
        f"SELECT json {base} ORDER BY thread_id DESC LIMIT ? OFFSET ?",
        (per_page, (page - 1) * per_page)
    ).fetchall()
    return [json.loads(r[0]) for r in rows if r], total


def search_orders(conn, keyword: str, page=1, per_page=10):
    """Search orders with SQL pre-filter then Python accent-insensitive match."""
    from bot_core.utils import _norm
    norm_kw = _norm(keyword)
    # SQL pre-filter: basic LIKE on raw text to reduce rows
    like_pattern = f"%{keyword[:20]}%"
    rows = conn.execute(
        "SELECT json FROM orders WHERE deleted_at IS NULL "
        "AND thread_id IS NOT NULL "
        "AND json_extract(json, '$.text') IS NOT NULL "
        "AND json_extract(json, '$.text') != '' "
        "AND json_extract(json, '$.created') >= '2026-04-01' "
        "AND json_extract(json, '$.text') LIKE ? "
        "ORDER BY thread_id DESC", (like_pattern,)
    ).fetchall()
    matched = []
    for r in rows:
        o = json.loads(r[0])
        if norm_kw in _norm(o.get("text", "")):
            matched.append(o)
    total = len(matched)
    start = (page - 1) * per_page
    return matched[start:start + per_page], total
