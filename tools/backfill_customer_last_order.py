"""Backfill last_order_at cho customers từ orders.created — chạy 1 lần.

Usage: .venv/bin/python tools/backfill_customer_last_order.py [--dry-run]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.db import get_connection
from utils.paths import SHARED_DB_PATH


def backfill(dry_run: bool = False):
    conn = get_connection(SHARED_DB_PATH)
    rows = conn.execute(
        """SELECT json_extract(json, '$.khach_hang_id') AS kh_id,
                  MAX(json_extract(json, '$.created')) AS latest
           FROM orders
           WHERE deleted_at IS NULL
             AND json_extract(json, '$.khach_hang_id') IS NOT NULL
             AND json_extract(json, '$.khach_hang_id') != ''
           GROUP BY kh_id"""
    ).fetchall()

    updated = 0
    for row in rows:
        kh_id, latest = row["kh_id"], row["latest"]
        if not kh_id or not latest:
            continue
        cust_row = conn.execute(
            "SELECT json FROM customers WHERE firebase_key = ? AND deleted_at IS NULL",
            (kh_id,),
        ).fetchone()
        if not cust_row:
            continue
        data = json.loads(cust_row["json"])
        existing = data.get("last_order_at") or ""
        if existing >= latest:
            continue
        data["last_order_at"] = latest
        if dry_run:
            print(f"  [dry-run] {kh_id}: {existing!r} -> {latest}")
        else:
            conn.execute(
                "UPDATE customers SET json = ? WHERE firebase_key = ?",
                (json.dumps(data, ensure_ascii=False), kh_id),
            )
        updated += 1

    if not dry_run:
        conn.commit()
    conn.close()
    print(f"{'[dry-run] ' if dry_run else ''}Updated {updated}/{len(rows)} customers")


if __name__ == "__main__":
    backfill(dry_run="--dry-run" in sys.argv)
