"""bot_don_hang/firebase_rtdb.py — Minimal Firebase RTDB writer."""
import json
import os

import firebase_admin
from firebase_admin import credentials, db

_app = None


def _get_app():
    global _app
    if _app is not None:
        return _app

    cred_file = os.getenv(
        "FIREBASE_CRED_FILE",
        os.path.expanduser("~/Documents/final_telegram/config/credentials/lt-4-asia-backup-firebase-adminsdk-fbsvc-455a8e080f.json"),
    )
    if cred_file and os.path.exists(cred_file):
        cred = credentials.Certificate(cred_file)
    else:
        cred_json = os.getenv("FIREBASE_SERVICE_ACCOUNT", "")
        if cred_json:
            cred = credentials.Certificate(json.loads(cred_json))
        else:
            return None

    database_url = os.getenv(
        "FIREBASE_DATABASE_URL",
        "https://lt-4-asia-backup-default-rtdb.asia-southeast1.firebasedatabase.app",
    )
    _app = firebase_admin.initialize_app(cred, {"databaseURL": database_url})
    return _app


def get_ref(path: str):
    app = _get_app()
    if not app:
        return None
    return db.reference(path, app=app)
