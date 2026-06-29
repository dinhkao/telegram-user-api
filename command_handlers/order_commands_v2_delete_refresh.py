from __future__ import annotations

import logging

from .order_commands_v2_utils import refresh_main_msg

log = logging.getLogger("order_commands_v2")


async def refresh_after_soft_delete(client, db_conn, thread_id, order):
    """Refresh main channel message after soft-delete so the
    'ĐÃ XÓA' banner shows up. Silent if no channel/message ids.
    Caller passes `order` (already fetched with include_deleted=True).
    """
    channel_id = order.get("channel_id")
    message_id = order.get("message_id")
    if not channel_id or not message_id:
        return
    try:
        await refresh_main_msg(client, db_conn, thread_id, channel_id, message_id)
    except Exception as e:
        log.warning("refresh after del failed thread=%d: %s", thread_id, e)