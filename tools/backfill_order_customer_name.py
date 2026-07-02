"""Backfill customer_name cho orders có khach_hang_id nhưng customer_name rỗng.

Khi customer_name rỗng, has_customer=0 → đơn bị ẩn khỏi filter pending/done
trên dashboard, và search theo tên khách không tìm được.

Usage: .venv/bin/python tools/backfill_order_customer_name.py [--dry-run]
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
    customers = {}
    for row in conn.execute("SELECT firebase_key, json FROM customers WHERE deleted_at IS NULL").fetchall():
        try:
            data = json.loads(row["json"])
            customers[row["firebase_key"]] = data.get("name") or data.get("ten") or row["firebase_key"]
        except Exception:
            continue

    rows = conn.execute(
        """SELECT thread_id, json FROM orders
           WHERE deleted_at IS NULL
             AND json_extract(json, '$.khach_hang_id') IS NOT NULL
             AND json_extract(json, '$.khach_hang_id') != ''
             AND (json_extract(json, '$.customer_name') IS NULL
                  OR json_extract(json, '$.customer_name') = '')"""
    ).fetchall()

    updated = 0
    missing_customer = 0
    for row in rows:
        try:
            data = json.loads(row["json"])
        except Exception:
            continue
        kh_id = str(data.get("khach_hang_id", ""))
        name = customers.get(kh_id)
        if not name:
            missing_customer += 1
            continue
        data["customer_name"] = name
        if dry_run:
            if updated < 10:
                print(f"  [dry-run] thread={row['thread_id']} kh_id={kh_id} -> {name}")
        else:
            conn.execute(
                "UPDATE orders SET json = json_set(json, '$.customer_name', ?) WHERE thread_id = ?",
                (name, row["thread_id"]),
            )
        updated += 1

    if not dry_run:
        conn.commit()
    conn.close()
    prefix = "[dry-run] " if dry_run else ""
    print(f"{prefix}Updated {updated}/{len(rows)} orders (skipped {missing_customer} with unknown customer)")


if __name__ == "__main__":
    backfill(dry_run="--dry-run" in sys.argv)
