"""DonHangDB: #don_hang message-index store (own SQLite `messages` table, migrations/reads/writes/search). Root shim: donhang_db.py."""
from .api import DonHangDB

__all__ = ["DonHangDB"]
