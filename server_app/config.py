from __future__ import annotations

import os
import pathlib

from dotenv import load_dotenv
from utils.logger import configure_logging

load_dotenv()
configure_logging()

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
PHONE = os.getenv("PHONE", "")
PORT = int(os.getenv("PORT", 8080))
SESSION = os.getenv("SESSION", "user_session")
GROUP_ID = int(os.getenv("GROUP_ID", 0))
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
DON_HANG_CHAT_ID = int(os.getenv("DONHANG_CHAT_ID", "-1002138495144"))
DON_HANG_QUERY = "#don_hang"
DON_HANG_BATCH = 50
DON_HANG_DB_PATH = os.getenv("DONHANG_DB", "donhang.db")
from utils.paths import SHARED_DB_PATH
AI_BACKEND = os.getenv("AI_BACKEND", "pi")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY", "")
PI_MODEL = os.getenv("PI_MODEL", "fireworks/accounts/fireworks/routers/kimi-k2p5-turbo")
FIREWORKS_MODEL = os.getenv("FIREWORKS_MODEL", "accounts/fireworks/routers/kimi-k2p5-turbo")
if FIREWORKS_MODEL.startswith("fireworks/"):
    FIREWORKS_MODEL = FIREWORKS_MODEL[len("fireworks/"):]
PI_SESSIONS_DIR = pathlib.Path(os.getenv("PI_SESSIONS_DIR", os.path.expanduser("~/.pi/agent/tg-sessions")))
PI_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
SEARCH_BATCH = 50
SEARCH_MAX_DEEP = 5000
RESULT_CACHE_TTL_SEC = 30
SYSTEM_PROMPT = "You are a helpful assistant in a Telegram group chat. Keep answers concise and clear."
MAX_HISTORY = 20
