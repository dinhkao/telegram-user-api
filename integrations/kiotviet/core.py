from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

log = logging.getLogger("kiotviet")
KIOTVIET_BASE = os.getenv("KIOTVIET_BASE_URL", "https://public.kiotapi.com")
KIOTVIET_TOKEN_URL = os.getenv("KIOTVIET_TOKEN_URL", "https://id.kiotviet.vn/connect/token")
# Secret KHÔNG hardcode trong source — đọc từ env (.env, gitignored). Bí mật cũ đã
# lộ trong git history → CẦN XOAY (rotate) ở KiotViet; xem REVIEW_REPORT.md.
KIOTVIET_CLIENT_ID = os.getenv("KIOTVIET_CLIENT_ID", "")
KIOTVIET_CLIENT_SECRET = os.getenv("KIOTVIET_CLIENT_SECRET", "")
if not KIOTVIET_CLIENT_SECRET:
    log.warning("KIOTVIET_CLIENT_SECRET chưa đặt trong env — gọi KiotViet sẽ thất bại")
KIOTVIET_RETAILER = os.getenv("KIOTVIET_RETAILER", "letrangphat")
_token: str | None = None
_token_expires = 0.0


def _refresh_token() -> None:
    global _token, _token_expires
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": KIOTVIET_CLIENT_ID,
        "client_secret": KIOTVIET_CLIENT_SECRET,
    }).encode()
    req = urllib.request.Request(
        KIOTVIET_TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
    _token = result["access_token"]
    _token_expires = time.time() + result.get("expires_in", 3600)
    log.info("KiotViet token refreshed, expires in %ds", result.get("expires_in", 3600))


def _request(method: str, path: str, body: dict | None = None,
             query_params: dict | None = None, retry: bool = True,
             timeout: int = 30) -> dict[str, Any]:
    global _token
    if not KIOTVIET_CLIENT_ID:
        raise RuntimeError("KIOTVIET_CLIENT_ID not configured")
    if not _token or time.time() > _token_expires - 60:
        _refresh_token()
    url = f"{KIOTVIET_BASE}{path}"
    if query_params:
        url += "?" + urllib.parse.urlencode(query_params)
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode() if body else None,
        headers={
            "Authorization": f"Bearer {_token}",
            "Retailer": KIOTVIET_RETAILER,
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 401 and retry:
            log.warning("KiotViet token expired, refreshing...")
            _token = None
            return _request(method, path, body, query_params, retry=False, timeout=timeout)
        text = e.read().decode(errors="replace")
        log.error("KiotViet HTTP %d %s: %s", e.code, path, text[:300])
        raise RuntimeError(f"KiotViet API error {e.code}: {text[:200]}") from e
    except urllib.error.URLError as e:
        if hasattr(e, "reason") and isinstance(e.reason, TimeoutError):
            log.error("KiotViet timeout %s after %ds", path, timeout)
        else:
            log.error("KiotViet request failed %s: %s", path, e)
        raise
    except Exception as e:
        log.error("KiotViet request failed %s: %s", path, e)
        raise
