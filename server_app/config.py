from __future__ import annotations

import os

from dotenv import load_dotenv
from utils.logger import configure_logging

load_dotenv()
configure_logging()

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
PHONE = os.getenv("PHONE", "")
PORT = int(os.getenv("PORT", 8080))
SESSION = os.getenv("SESSION", "user_session")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
DON_HANG_CHAT_ID = int(os.getenv("DONHANG_CHAT_ID", "-1002138495144"))
DON_HANG_QUERY = "#don_hang"
DON_HANG_BATCH = 50
DON_HANG_DB_PATH = os.getenv("DONHANG_DB", "donhang.db")
from utils.paths import SHARED_DB_PATH
# Web app auth (server_app/web_auth/) — bật chặn /api/* bằng WEB_AUTH_ENABLED=true.
WEB_AUTH_ENABLED = os.getenv("WEB_AUTH_ENABLED", "false").strip().lower() in ("1", "true", "yes")
WEB_AUTH_TOKEN_TTL = int(os.getenv("WEB_AUTH_TOKEN_TTL", 30 * 24 * 3600))  # 30 ngày
# Web user được phép xoá hoá đơn KiotViet (chỉ Duy). Đổi qua env nếu cần.
ADMIN_WEB_USER = os.getenv("ADMIN_WEB_USER", "duy")
# CORS allowlist cho web app (WebView APK + dev); thêm origin qua env, phẩy ngăn cách.
WEB_CORS_ORIGINS = tuple(
    o.strip() for o in os.getenv(
        "WEB_CORS_ORIGINS",
        "https://appassets.androidplatform.net,http://localhost:5174,http://127.0.0.1:5174",
    ).split(",") if o.strip()
)
MAX_HISTORY = 20
