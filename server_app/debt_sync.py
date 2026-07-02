"""On-demand customer debt refresh from KiotViet.

Debt is updated event-driven (invoice create/delete, payment, channel
render) via order_store.update_customer_debt(). This module provides
refresh_single_debt() for the /api/customers/{key}/refresh-debt endpoint.
Connects to: integrations/kiotviet, order_store/customers (app.db).
"""
from __future__ import annotations

import json
import logging
import time

from utils.db import get_connection
from utils.paths import SHARED_DB_PATH

log = logging.getLogger("debt_sync")


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
