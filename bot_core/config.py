"""bot_core/config.py — Bot-specific configuration.

Reads from same .env as telegram-user-api. Bot-specific values (BOT_TOKEN,
PRODUCT_CODES, etc.) are defined here.
"""
import os

# ─── Telegram ───────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# ─── Groups (override in .env if needed) ────────────────────────────────────
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", os.getenv("ORDER_GROUP_ID", "-1002124542200")))
DISCUSSION_GROUP_CHAT_ID = int(os.getenv("DISCUSSION_GROUP_CHAT_ID", "-1003776216538"))
PRODUCTION_GROUP_ID = int(os.getenv("PRODUCTION_GROUP_ID", "-1002309480904"))
PRODUCTION_CHANNEL_ID = int(os.getenv("PRODUCTION_CHANNEL_ID", "-1002464385161"))

# ─── Backend (now same process, but keep for compatibility) ─────────────────
ORDER_API_BASE = os.getenv("ORDER_API_BASE", "http://localhost:8090")
USER_API_BASE = os.getenv("USER_API_BASE", "http://localhost:8090")

# ─── SQLite (shared with telegram-user-api) ─────────────────────────────────
from pathlib import Path
DB_PATH = Path(os.getenv("SHARED_DB_PATH", os.path.expanduser("~/letrang-db/app.db")))

# ─── HTTP ───────────────────────────────────────────────────────────────────
BOT_HTTP_PORT = int(os.getenv("BOT_HTTP_PORT", "3002"))

# ─── API keys for downstream services ───────────────────────────────────────
USER_API_KEY = os.getenv("USER_API_KEY", "")


# ─── Users & admins (parsed from env) ──────────────────────────────────────
def _parse_users(raw: str) -> dict[str, str]:
    """Parse 'uid=name,uid=name' → {'uid': 'name'}."""
    out: dict[str, str] = {}
    if not raw:
        return out
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        uid, name = pair.split("=", 1)
        out[uid.strip()] = name.strip()
    return out


USER_NAMES = _parse_users(
    os.getenv(
        "USER_NAMES",
        "1809874974=Duy,6970077624=Tùng,6964088058=Trinh,7569624990=Tuấn,6730500620=Trang,7158345531=Trí",
    )
)
ALLOWED_USER_IDS = set(USER_NAMES.keys())
ADMIN_IDS = set(os.getenv("ADMIN_IDS", "1809874974,6730500620").split(","))


# ─── Product codes ──────────────────────────────────────────────────────────
PRODUCT_CODE_ROWS = [
    ["K10LV87", "K10LV85", "K10LT"],
    ["K2L", "K2NT", "K2NV128", "K2NV120", "K1L"],
    ["KD2M", "KDBN2M", "KDBN1L"],
    ["DMX", "DM50", "DM180", "DM450"],
    ["KDDT", "KDDT200", "KDDT470"],
    ["KDXDB", "KDXL1", "KDG"],
    ["KGL", "KMT", "KMD", "KHDX"],
    ["KDV380DB", "KDV470DB", "KGL250"],
    ["K10TV80", "K10NV60"],
]
PRODUCT_CODES = [c for row in PRODUCT_CODE_ROWS for c in row]
QTY_OPTIONS = ["1", "5", "10", "20", "30", "40", "50", "100", "150", "200", "250", "300"]
QTY_OPTIONS_BY_CODE = {"KDDT": ["1", "2", "3", "6", "9", "12", "15", "18", "21", "24", "27", "30"]}


# ─── Sản xuất (production) ──────────────────────────────────────────────────
# mâm = số mâm trong 1 chảo, luong = lượng SP mỗi mẻ (ported from node spInfo).
SP_INFO = {
    "K10LV87": {"mam": 3, "luong": 1100},
    "K10LT": {"mam": 3, "luong": 1200},
    "K10LV85": {"mam": 3, "luong": 1000},
    "K10NV60": {"mam": 5, "luong": 500},
    "K10TV80": {"mam": 4, "luong": 800},
    "K2L": {"mam": 3.5, "luong": 720},
    "K2NT128": {"mam": 6, "luong": 400},
    "K2NV120": {"mam": 6, "luong": 380},
    "K2NV128": {"mam": 6, "luong": 380},
    "KDDT": {"mam": 5, "luong": 700},
    "KD2M": {"mam": 6, "luong": 900},
    "KDBN2M": {"mam": 4.5, "luong": 1000},
    "KDBN1L": {"mam": 4, "luong": 1000},
    "K1L": {"mam": 4, "luong": 720},
}

# Cây trong 1 chảo (ported from node cayTrong1Chao).
CAY_TRONG_1_CHAO = {
    "K10LT": 18,
    "K10LV87": 19,
    "K10LV-87M": 18,
    "K10LV85": 25,
    "K10TV80": 27,
    "K10NV60": 44,
    "K2L": 31,
    "K1L": 25,
    "K2LBN": 33,
    "K2L DÀY": 31,
    "KE": 27,
    "K2NT128": 36,
    "K2NV128": 47,
    "K2NV120": 54,
    "KD2M": 40,
    "KDBN2M": 30,
    "KDBN1L": 28,
    "KDDT": 330,
    "KDDT10M": 16,
    "KDDT2": 160,
}


def name_of_user_id(uid) -> str | None:
    return USER_NAMES.get(str(uid))


def is_allowed(uid) -> bool:
    """Whitelist check. Set ALLOW_ALL_USERS=1 to disable gating."""
    if os.getenv("ALLOW_ALL_USERS", "0") == "1":
        return True
    return str(uid) in ALLOWED_USER_IDS


def is_admin(uid) -> bool:
    return str(uid) in ADMIN_IDS
