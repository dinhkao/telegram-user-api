"""firebase_sync.py — Firebase RTDB read/write for telegram-user-api.

Shares the same Firebase project as final_telegram.
Writes go directly to the RTDB; Node.js reads from both SQLite and RTDB
so the two processes stay in sync.
"""
from __future__ import annotations
import json
import logging
import os

import firebase_admin
from firebase_admin import credentials, db

log = logging.getLogger("firebase_sync")

# ── Init ────────────────────────────────────────────────────────────

_app = None
DONHANG_PATH = os.getenv("FIREBASE_DONHANG_PATH", "donhang_new_chuaxong")

def _get_app():
    global _app
    if _app is not None:
        return _app

    # Use the same credential file as final_telegram Node.js to avoid 401 errors
    cred_file = os.getenv(
        "FIREBASE_CRED_FILE",
        os.path.expanduser("~/Documents/final_telegram/config/credentials/lt-4-asia-backup-firebase-adminsdk-fbsvc-455a8e080f.json"),
    )
    if cred_file and os.path.exists(cred_file):
        cred = credentials.Certificate(cred_file)
    else:
        # Fallback to env var JSON (legacy)
        cred_json = os.getenv("FIREBASE_SERVICE_ACCOUNT", "")
        if cred_json:
            cred = credentials.Certificate(json.loads(cred_json))
        else:
            log.warning("FIREBASE_CRED_FILE not found — Firebase writes disabled")
            return None

    database_url = os.getenv(
        "FIREBASE_DATABASE_URL",
        "https://lt-4-asia-backup-default-rtdb.asia-southeast1.firebasedatabase.app",
    )

    _app = firebase_admin.initialize_app(cred, {"databaseURL": database_url})
    log.info("Firebase initialized: %s", database_url)
    return _app


def _ref(path: str):
    """Get a Firebase DB reference, or None if not configured."""
    app = _get_app()
    if app is None:
        return None
    return db.reference(path, app=app)


# ── Public API ─────────────────────────────────────────────────────

def get_order(thread_id: int | str) -> dict | None:
    """Read full order data from Firebase RTDB."""
    r = _ref(f"{DONHANG_PATH}/{thread_id}")
    if r is None:
        return None
    return r.get()


def set_order(thread_id: int | str, data: dict) -> bool:
    """Write full order data to Firebase RTDB."""
    r = _ref(f"{DONHANG_PATH}/{thread_id}")
    if r is None:
        return False
    data["updated_at"] = _now_iso()
    r.set(data)
    return True


def update_order(thread_id: int | str, updates: dict) -> bool:
    """Patch specific fields of an order in Firebase RTDB."""
    r = _ref(f"{DONHANG_PATH}/{thread_id}")
    if r is None:
        return False
    updates["updated_at"] = _now_iso()
    r.update(updates)
    return True


def set_fund_receipt(receipt_id: str, data: dict) -> bool:
    """Write a fund receipt (phiếu thu chi) to Firebase."""
    r = _ref(f"quy/phieu_thu_chi/{receipt_id}")
    if r is None:
        return False
    r.set(data)
    return True


def get_fund_receipts() -> dict:
    """Read all fund receipts."""
    r = _ref("quy/phieu_thu_chi")
    if r is None:
        return {}
    return r.get() or {}


# ── Helpers ────────────────────────────────────────────────────────

def _now_iso() -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
