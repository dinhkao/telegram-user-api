"""sheets_bot.config — env reading + credential resolution.

Nothing here touches the network or requires credentials at *import* time.
`get_service()` / `get_credentials()` are lazy and only resolve creds when first
called (i.e. at bot start time), so the module imports cleanly with no env set.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading

log = logging.getLogger("sheets_bot.config")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


# ---------------------------------------------------------------------------
# Spreadsheet ids / gids  (same defaults as bot.js — these are document ids,
# not secrets; tokens/credentials are never hardcoded)
# ---------------------------------------------------------------------------
def spreadsheet_id() -> str:
    return os.getenv("SPREADSHEET_ID") or "18n-W71c81rYHfFR1eq6rp-YLml8301UW4XhmJtcYvqo"


def topic_spreadsheet_id() -> str:
    return os.getenv("TOPIC_SPREADSHEET_ID") or "1zSCustpTviHF4-bb8BrFft_K8wdZ9pYUFbsh2eoqyVk"


def topic_sheet_gid() -> int:
    return int(os.getenv("TOPIC_SHEET_GID") or "1962815338")


def allowed_products_gid() -> int:
    return int(os.getenv("ALLOWED_PRODUCTS_GID") or "811594671")


def allowed_products_cache_ms() -> int:
    return int(os.getenv("ALLOWED_PRODUCTS_CACHE_MS") or "300000")


def import_sheet_gid() -> int:
    return int(os.getenv("IMPORT_SHEET_GID") or "2031606130")


def bot_token() -> str | None:
    return os.getenv("SHEETS_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")


def _is_placeholder(val: str | None) -> bool:
    if not val:
        return True
    v = val.lower()
    return (
        "your_telegram_bot_token" in v
        or "your_sheet_id" in v
        or "path/to/credentials.json" in v
    )


# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------
def _resolve_credentials_info() -> dict | None:
    """Return the service-account JSON as a dict, from one of:

    - GOOGLE_APPLICATION_CREDENTIALS: a file path, OR inline JSON starting with '{'
    - GOOGLE_APPLICATION_CREDENTIALS_JSON: raw JSON
    - GOOGLE_APPLICATION_CREDENTIALS_B64: base64-encoded JSON
    """
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path and not _is_placeholder(cred_path) and os.path.exists(cred_path):
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


_lock = threading.Lock()
_credentials = None
_service = None


def get_credentials():
    """Return (and memoize) a google.oauth2.service_account.Credentials."""
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
    """Return (and memoize) a Sheets API v4 service."""
    global _service
    with _lock:
        if _service is None:
            from googleapiclient.discovery import build

            _service = build(
                "sheets", "v4", credentials=get_credentials(), cache_discovery=False
            )
        return _service


def get_access_token() -> str | None:
    """Return a valid OAuth2 access token for gviz REST queries."""
    from google.auth.transport.requests import Request

    creds = get_credentials()
    if not creds.valid:
        creds.refresh(Request())
    return creds.token
