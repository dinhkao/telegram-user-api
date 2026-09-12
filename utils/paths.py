"""Central filesystem / DB paths — single source of truth.

Every module that needs a shared DB location imports it from here instead of
re-deriving `os.path.expanduser(os.getenv("SHARED_DB_PATH", ...))` on its own.
Override any of these via the matching env var. Depends on nothing in the
project (safe to import anywhere — no cycles).

Connects to: read by order_store, chat_log, audit, bot_core, command_handlers,
server_app.config — the SQLite stores.
"""
from __future__ import annotations

import os

# Shared SQLite DB (orders / customers / notes / quỹ). Shared with the Node app.
# Unexpanded default kept as a constant so callers that need the raw form match.
DEFAULT_SHARED_DB = "~/letrang-db/app.db"
SHARED_DB_PATH = os.path.expanduser(os.getenv("SHARED_DB_PATH", DEFAULT_SHARED_DB))

# Local index of the #don_hang channel (rebuildable from Telegram).
DONHANG_DB_PATH = os.path.expanduser(os.getenv("DONHANG_DB", "donhang.db"))

# User-uploaded order images (full + thumbnail files), one subdir per thread_id.
# Filesystem store sibling of app.db; DB holds only metadata (order_images_store).
ORDER_MEDIA_DIR = os.path.expanduser(os.getenv("ORDER_MEDIA_DIR", "~/letrang-db/media"))

# Thư mục TẠM của tiến trình.
# aiohttp `request.post()` ghi MỖI phần file của multipart ra `tempfile.TemporaryFile()`,
# và renderers HTML→PNG cũng ghi file tạm ⇒ mặc định rơi vào TMPDIR = /var/folders/…
# nằm trên Ổ TRONG của máy. Ổ trong nhỏ + hay đầy (đã gây `[Errno 28] No space left on
# device` làm hỏng render phiếu thu/hoá đơn và upload ảnh), trong khi app.db + ảnh đều
# nằm trên SSD ngoài qua ~/letrang-db. Nên trỏ thư mục tạm sang cạnh chúng: mọi byte
# của một lần upload ảnh đi thẳng vào SSD, không chạm ổ trong.
APP_TMP_DIR = os.path.expanduser(os.getenv("APP_TMP_DIR", "~/letrang-db/tmp"))


def use_app_tmpdir(max_age_hours: float = 24.0) -> str | None:
    """Chuyển thư mục tạm của tiến trình sang APP_TMP_DIR (SSD) + dọn rác cũ.

    Gọi MỘT LẦN lúc boot, TRƯỚC khi phục vụ request. Đặt cả `tempfile.tempdir`
    (cho tiến trình này) lẫn `TMPDIR` (cho tiến trình con: playwright, ffmpeg…).
    SSD chưa mount / không ghi được → giữ nguyên mặc định hệ thống, trả None.
    """
    import tempfile
    import time

    try:
        os.makedirs(APP_TMP_DIR, exist_ok=True)
        probe = os.path.join(APP_TMP_DIR, ".write-probe")
        with open(probe, "wb") as f:
            f.write(b"1")
        os.unlink(probe)
    except OSError:
        return None

    tempfile.tempdir = APP_TMP_DIR
    os.environ["TMPDIR"] = APP_TMP_DIR

    # Dọn file tạm mồ côi (tiến trình chết giữa chừng) để thư mục không phình mãi.
    cutoff = time.time() - max_age_hours * 3600
    try:
        for name in os.listdir(APP_TMP_DIR):
            p = os.path.join(APP_TMP_DIR, name)
            try:
                if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                    os.unlink(p)
            except OSError:
                pass
    except OSError:
        pass
    return APP_TMP_DIR
