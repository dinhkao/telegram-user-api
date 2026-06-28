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


def name_of_user_id(uid) -> str | None:
    return USER_NAMES.get(str(uid))


def is_allowed(uid) -> bool:
    """Whitelist check. Set ALLOW_ALL_USERS=1 to disable gating."""
    if os.getenv("ALLOW_ALL_USERS", "0") == "1":
        return True
    return str(uid) in ALLOWED_USER_IDS


def is_admin(uid) -> bool:
    return str(uid) in ADMIN_IDS
