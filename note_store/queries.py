from __future__ import annotations
import json

# Columns that map 1:1 into the `notes` table (see schema.py). The public
# dict shape returned by get_note() renames check_flag/del_flag -> check/del
# to mirror the node/Firebase note object (`note.check`, `note.del`).
_COLUMNS = (
    "thread_id",
    "text",
    "tags",
    "check_flag",
    "del_flag",
    "channel_id",
    "message_id",
    "updated_at",
)


def get_note(conn, thread_id) -> dict | None:
    row = conn.execute("SELECT * FROM notes WHERE thread_id = ?", (thread_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    try:
        tags = json.loads(data.get("tags")) if data.get("tags") else []
    except (TypeError, ValueError):
        tags = []
    return {
        "thread_id": data.get("thread_id"),
        "text": data.get("text"),
        "tags": tags if isinstance(tags, list) else [],
        "check": bool(data.get("check_flag")),
        "del": bool(data.get("del_flag")),
        "channel_id": data.get("channel_id"),
        "message_id": data.get("message_id"),
        "updated_at": data.get("updated_at"),
    }


def _update(conn, thread_id, **fields) -> bool:
    """UPDATE-only (note creation is out of scope for this port — a note row
    must already exist, exactly like node's `if (!note) return`)."""
    if not fields:
        return False
    updates, params = [], []
    for key, value in fields.items():
        if key not in _COLUMNS or key == "thread_id":
            continue
        if key == "tags":
            value = json.dumps(value, ensure_ascii=False)
        updates.append(f"{key} = ?")
        params.append(value)
    if not updates:
        return False
    updates.append("updated_at = datetime('now')")
    params.append(thread_id)
    cur = conn.execute(f"UPDATE notes SET {', '.join(updates)} WHERE thread_id = ?", params)
    conn.commit()
    return cur.rowcount > 0


def set_text(conn, thread_id, text) -> bool:
    return _update(conn, thread_id, text=text)


def set_tags(conn, thread_id, tags) -> bool:
    return _update(conn, thread_id, tags=tags)


def set_check(conn, thread_id, check: bool) -> bool:
    return _update(conn, thread_id, check_flag=1 if check else 0)


def set_del(conn, thread_id, del_flag: bool = True) -> bool:
    return _update(conn, thread_id, del_flag=1 if del_flag else 0)
