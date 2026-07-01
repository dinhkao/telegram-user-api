"""Order-note store: schema + queries (text/tags/check/del) -> shared SQLite (app.db)."""
from .schema import create_note_table, migrate_note_table
from .queries import (
    get_note,
    set_text,
    set_tags,
    set_check,
    set_del,
)

__all__ = [
    "create_note_table",
    "migrate_note_table",
    "get_note",
    "set_text",
    "set_tags",
    "set_check",
    "set_del",
]
