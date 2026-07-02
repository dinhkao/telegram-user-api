"""Background task: refresh customer debt from KiotViet every 30 min.

Only refreshes active customers (ordered in last 30 days). Connects to:
integrations/kiotviet, order_store/customers (app.db).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta

from utils.db import get_connection
from utils.paths import SHARED_DB_PATH

log = logging.getLogger("debt_sync")
INTERVAL = 30 * 60


async def debt_sync_loop():
    await asyncio.sleep(60)
    while True:
        try:
            updated = await asyncio.to_thread(_sync_active_debts)
            if updated:
                log.info("debt_sync: refreshed %d customers", updated)
        except Exception as e:
            log.warning("debt_sync failed: %s", e)
        await asyncio.sleep(INTERVAL)


def _sync_active_debts() -> int:
    from integrations.kiotviet.customers import get_customer_debt_kv

    conn = get_connection(SHARED_DB_PATH)
    cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    rows = conn.execute(
        """SELECT firebase_key, json FROM customers
           WHERE deleted_at IS NULL
             AND json_extract(json, '$.last_order_at') >= ?
             AND json_extract(json, '$.kh_id') IS NOT NULL""",
        (cutoff,),
    ).fetchall()

    updated = 0
    now_ms = int(time.time() * 1000)
    for row in rows:
        try:
            data = json.loads(row["json"])
            kv_id = data.get("kh_id")
            if not kv_id:
                continue
            det = get_customer_debt_kv(int(kv_id))
            new_debt = det.get("debt")
            if new_debt is None:
                continue
            old_debt = data.get("debt")
            if old_debt == new_debt:
                data["debt_updated_at"] = now_ms
                conn.execute(
                    "UPDATE customers SET json = json_set(json, '$.debt_updated_at', ?) WHERE firebase_key = ?",
                    (now_ms, row["firebase_key"]),
                )
                continue
            data["debt"] = new_debt
            data["debt_updated_at"] = now_ms
            conn.execute(
                "UPDATE customers SET json = ?, updated_at = ? WHERE firebase_key = ?",
                (json.dumps(data, ensure_ascii=False), now_ms, row["firebase_key"]),
            )
            updated += 1
        except Exception as e:
            log.warning("debt_sync: key=%s error=%s", row["firebase_key"], e)
            time.sleep(1)
    conn.commit()
    conn.close()
    return updated


def refresh_single_debt(firebase_key: str) -> dict | None:
    """Fetch live debt for one customer from KiotViet. Returns updated data or None."""
    from integrations.kiotviet.customers import get_customer_debt_kv

    conn = get_connection(SHARED_DB_PATH)
    try:
        row = conn.execute(
            "SELECT json FROM customers WHERE firebase_key = ? AND deleted_at IS NULL",
            (firebase_key,),
        ).fetchone()
        if not row:
            return None
        data = json.loads(row["json"])
        kv_id = data.get("kh_id")
        if not kv_id:
            return data
        det = get_customer_debt_kv(int(kv_id))
        new_debt = det.get("debt")
        if new_debt is None:
            return data
        now_ms = int(time.time() * 1000)
        data["debt"] = new_debt
        data["debt_updated_at"] = now_ms
        conn.execute(
            "UPDATE customers SET json = ?, updated_at = ? WHERE firebase_key = ?",
            (json.dumps(data, ensure_ascii=False), now_ms, firebase_key),
        )
        conn.commit()
        return data
    finally:
        conn.close()
