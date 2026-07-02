"""Băm & kiểm tra PIN — logic thuần (stdlib pbkdf2), không IO, unit-test được.

Format lưu DB: "pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>".
Dùng bởi: user_store.users. Không import gì trong project.
"""
from __future__ import annotations

import hashlib
import hmac
import os

_ALGO = "pbkdf2_sha256"
_DEFAULT_ITERATIONS = 200_000


def hash_pin(pin: str, *, iterations: int = _DEFAULT_ITERATIONS, _salt: bytes | None = None) -> str:
    """Băm PIN → chuỗi tự mô tả (algo + iterations + salt + hash)."""
    salt = _salt if _salt is not None else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)
    return f"{_ALGO}${iterations}${salt.hex()}${digest.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    """So PIN với chuỗi đã lưu — constant-time, sai format trả False (không raise)."""
    try:
        algo, iters_s, salt_hex, hash_hex = stored.split("$")
        if algo != _ALGO:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(salt_hex), int(iters_s))
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False
