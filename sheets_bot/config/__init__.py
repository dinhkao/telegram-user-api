"""sheets_bot.config — env reading + credential resolution (aggregated)."""

from .creds import (
    SCOPES,
    get_access_token,
    get_credentials,
    get_service,
    has_credentials,
)
from .ids import (
    allowed_products_cache_ms,
    allowed_products_gid,
    bot_token,
    import_sheet_gid,
    is_placeholder,
    spreadsheet_id,
    topic_sheet_gid,
    topic_spreadsheet_id,
)

# Backwards-compatible alias (bot.py used config._is_placeholder).
_is_placeholder = is_placeholder

__all__ = [
    "SCOPES", "get_access_token", "get_credentials", "get_service",
    "has_credentials", "allowed_products_cache_ms", "allowed_products_gid",
    "bot_token", "import_sheet_gid", "is_placeholder", "_is_placeholder",
    "spreadsheet_id", "topic_sheet_gid", "topic_spreadsheet_id",
]
