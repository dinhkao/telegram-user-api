"""TẠO khoá VAPID (Web Push) 1 LẦN → file PEM ở VAPID_PRIVATE_KEY_FILE (chmod 600).

Đã có file thì KHÔNG ghi đè (đổi khoá = mọi máy đã bật thông báo phải bật lại) — muốn
tạo lại thật thì xoá file trước. In ra khoá công khai (base64url) để đối chiếu.
Nối: utils.paths.VAPID_PRIVATE_KEY_FILE, server_app.webpush.

    .venv/bin/python tools/gen_vapid_key.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

from utils.paths import VAPID_PRIVATE_KEY_FILE  # noqa: E402


def main():
    path = VAPID_PRIVATE_KEY_FILE
    if os.path.exists(path):
        print(f"Đã có khoá: {path} — không ghi đè.")
    else:
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(pem)
        print(f"Đã tạo khoá: {path}")
    from server_app.webpush import public_key
    print("Khoá công khai:", public_key())


if __name__ == "__main__":
    main()
