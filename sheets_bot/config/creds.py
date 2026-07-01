"""Service-account credential resolution + Sheets API service (all lazy).

Nothing here touches the network or requires credentials at *import* time.
Creds resolve only when first requested (i.e. at bot start time).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading

from .ids import is_placeholder

log = logging.getLogger("sheets_bot.config")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Reentrant: get_service() holds this lock and then calls get_credentials(),
# which re-acquires it on the same thread. A plain Lock would self-deadlock.
_lock = threading.RLock()
_credentials = None
_service = None


def _resolve_credentials_info() -> dict | None:
    """Return the service-account JSON as a dict, from path / raw JSON / base64."""
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path and not is_placeholder(cred_path) and os.path.exists(cred_path):
        try:
            with open(cred_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as err:  # noqa: BLE001
            log.error("Failed to read GOOGLE_APPLICATION_CREDENTIALS file: %s", err)

    inline_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON") or ""
    if not inline_json and cred_path and cred_path.strip().startswith("{"):
        inline_json = cred_path
    b64 = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_B64") or ""

    raw = ""
    if inline_json.strip():
        raw = inline_json.strip()
    elif b64.strip():
        try:
            raw = base64.b64decode(b64.strip()).decode("utf-8")
        except Exception as err:  # noqa: BLE001
            log.error("Failed to decode GOOGLE_APPLICATION_CREDENTIALS_B64: %s", err)

    if raw:
        try:
            return json.loads(raw)
        except Exception as err:  # noqa: BLE001
            log.error("Failed to parse service account JSON: %s", err)
    return None


def has_credentials() -> bool:
    return _resolve_credentials_info() is not None


def get_credentials():
    global _credentials
    with _lock:
        if _credentials is None:
            from google.oauth2.service_account import Credentials

            info = _resolve_credentials_info()
            if info is None:
                raise RuntimeError(
                    "Missing credentials. Set GOOGLE_APPLICATION_CREDENTIALS (file path), "
                    "or GOOGLE_APPLICATION_CREDENTIALS_JSON / GOOGLE_APPLICATION_CREDENTIALS_B64."
                )
            _credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
        return _credentials


def get_service():
    global _service
    with _lock:
        if _service is None:
            from googleapiclient.discovery import build

            _service = build("sheets", "v4", credentials=get_credentials(), cache_discovery=False)
        return _service


def get_access_token() -> str | None:
    from google.auth.transport.requests import Request

    creds = get_credentials()
    if not creds.valid:
        creds.refresh(Request())
    return creds.token
