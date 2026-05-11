"""receipt_print.py — Queue a payment receipt print job.

Mirrors the generatePaymentReceiptPrint() from Node.js.
Currently stores the print job in SQLite for the Node.js print worker to pick up.
"""
from __future__ import annotations
import json
import logging
import os
import sqlite3
import time

log = logging.getLogger("receipt_print")

SHARED_DB_PATH = os.path.expanduser(
    os.getenv("SHARED_DB_PATH", "~/Documents/final_telegram/data/app.db")
)


def queue_payment_receipt_print(
    thread_id: int,
    customer_name: str,
    payment_amount: int,
    old_debt: int | None = None,
    new_debt: int | None = None,
) -> bool:
    """Queue a payment receipt print job.
    
    Writes into the print_jobs table (shared SQLite).
    Node.js print worker picks it up and renders the receipt.
    """
    try:
        conn = sqlite3.connect(SHARED_DB_PATH, check_same_thread=False)
        conn.execute("PRAGMA busy_timeout=5000;")

        now_iso = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        job_data = {
            "type": "payment_receipt",
            "thread_id": thread_id,
            "customer_name": customer_name,
            "payment_amount": payment_amount,
            "old_debt": old_debt,
            "new_debt": new_debt,
            "created_at": now_iso,
        }

        # Ensure table exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS print_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_type TEXT NOT NULL DEFAULT 'payment_receipt',
                thread_id INTEGER,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT,
                processed_at TEXT
            )
        """)

        conn.execute(
            "INSERT INTO print_jobs (job_type, thread_id, payload, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
            ("payment_receipt", thread_id, json.dumps(job_data, ensure_ascii=False), now_iso),
        )
        conn.commit()
        conn.close()

        log.info("Print job queued: thread=%d customer=%s amount=%s", thread_id, customer_name, payment_amount)
        return True
    except Exception as e:
        log.warning("Failed to queue print job: %s", e)
        return False
