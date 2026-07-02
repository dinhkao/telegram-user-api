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
