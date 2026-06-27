from __future__ import annotations

import json
import logging
import os
import time

log = logging.getLogger("firebase_sync")
_app = None
firebase_app = None
DONHANG_PATH = os.getenv("FIREBASE_DONHANG_PATH", "donhang_new_chuaxong")
KHACH_HANG_PATH = os.getenv("FIREBASE_KHACH_HANG_PATH", "khach_hang")


def _get_app():
    import firebase_admin
    from firebase_admin import credentials

    global _app, firebase_app
    if _app is not None:
        return _app
    cred_file = os.getenv("FIREBASE_CRED_FILE", os.path.expanduser(
        "~/letrang-db/lt-4-asia-backup-firebase-adminsdk-fbsvc-455a8e080f.json"))
    if cred_file and os.path.exists(cred_file):
        cred = credentials.Certificate(cred_file)
    else:
        cred_json = os.getenv("FIREBASE_SERVICE_ACCOUNT", "")
        if not cred_json:
            log.warning("FIREBASE_CRED_FILE not found — Firebase writes disabled")
            return None
        cred = credentials.Certificate(json.loads(cred_json))
    database_url = os.getenv("FIREBASE_DATABASE_URL",
                             "https://lt-4-asia-backup-default-rtdb.asia-southeast1.firebasedatabase.app")
    _app = firebase_admin.initialize_app(cred, {"databaseURL": database_url})
    firebase_app = _app
    log.info("Firebase initialized: %s", database_url)
    return _app


def _ref(path: str):
    from firebase_admin import db

    app = _get_app()
    return None if app is None else db.reference(path, app=app)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
