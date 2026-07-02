"""Ký & kiểm token đăng nhập — HMAC-SHA256, logic thuần (secret truyền vào, không env).

Format: base64url(JSON {"u": username, "exp": unix}) + "." + hex(hmac).
Dùng bởi: web_auth.routes (issue), web_auth.middleware (verify). Unit-test: tests/test_web_auth.py.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json


def _sign(secret: str, payload_b64: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()


def issue_token(secret: str, username: str, *, ttl_seconds: int, now: int) -> str:
    payload = json.dumps({"u": username, "exp": now + ttl_seconds}, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{payload_b64}.{_sign(secret, payload_b64)}"


def verify_token(secret: str, token: str, *, now: int) -> str | None:
    """Token hợp lệ + chưa hết hạn → username; mọi lỗi khác → None (không raise)."""
    try:
        payload_b64, sig = token.split(".")
        if not hmac.compare_digest(_sign(secret, payload_b64), sig):
            return None
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        if int(payload["exp"]) < now:
            return None
        username = payload["u"]
        return username if isinstance(username, str) and username else None
    except Exception:
        return None
