from __future__ import annotations

import logging
import os

log = logging.getLogger("firebase_png")
_app = None


def _get_app():
    global _app
    if _app is not None:
        return _app
    import firebase_admin
    from firebase_admin import credentials

    cred_file = os.getenv("FIREBASE_PNG_CRED_FILE", os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "lt-4-asia-firebase-adminsdk-h742l-dd613bfebd.json",
    ))
    if not os.path.exists(cred_file):
        log.warning("Firebase PNG credential not found: %s", cred_file)
        return None
    db_url = os.getenv("FIREBASE_PNG_DATABASE_URL",
                       "https://lt-4-asia-default-rtdb.asia-southeast1.firebasedatabase.app")
    _app = firebase_admin.initialize_app(credentials.Certificate(cred_file), {"databaseURL": db_url}, name="png_print")
    log.info("Firebase PNG/Print initialized: %s", db_url)
    return _app


def ref(path: str):
    from firebase_admin import db

    app = _get_app()
    return None if app is None else db.reference(path, app=app)


def html_to_png_ref():
    return ref("html-to-png")


def meta_to_print_ref():
    return ref("meta/to_print")


def meta_to_print2_ref():
    return ref("meta/to_print2")
