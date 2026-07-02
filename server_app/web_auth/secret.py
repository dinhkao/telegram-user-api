"""Nguồn secret ký token web_auth — env WEB_AUTH_SECRET, không có thì file cạnh app.db.

File `web_auth_secret` tự sinh (32 byte hex, chmod 600) trong thư mục của
SHARED_DB_PATH → mọi lần restart giữ nguyên secret, token không bị vô hiệu.
Dùng bởi: web_auth.middleware, web_auth.routes.
"""
from __future__ import annotations

import os
import secrets as _secrets

from utils.paths import SHARED_DB_PATH

_cached: str | None = None


def get_web_auth_secret() -> str:
    global _cached
    if _cached:
        return _cached
    env = os.getenv("WEB_AUTH_SECRET", "").strip()
    if env:
        _cached = env
        return _cached
    path = os.getenv(
        "WEB_AUTH_SECRET_FILE",
        os.path.join(os.path.dirname(SHARED_DB_PATH), "web_auth_secret"),
    )
    if os.path.exists(path):
        with open(path, "r", encoding="ascii") as f:
            _cached = f.read().strip()
        if _cached:
            return _cached
    value = _secrets.token_hex(32)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write(value)
    _cached = value
    return _cached
