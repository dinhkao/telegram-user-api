"""order_store schema constants + connection/transaction — nay ủy quyền cho utils.db
(cổng SQLite trung tâm, điểm swap Postgres). Giữ tên `_get_connection`/`transaction`
để mọi importer cũ (order_store.*, order_db shim, server_app) không đổi."""
from __future__ import annotations
import logging

log = logging.getLogger("order_db")
from utils.paths import SHARED_DB_PATH
from utils.db import get_connection as _get_connection, transaction
MIRROR_FIELDS = {"soan_hang": "soan", "giao_hang": "giao", "nop_tien": "nop", "nhan_tien": "nhan"}
