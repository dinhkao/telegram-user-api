"""nop_tien_reminder.py — Timer reminder khi giao hang xong ma chua nop tien.

Khi giao hang duoc danh dau done, bat dau timer:
- Check sau 15 phut, neu nop_tien chua done -> gui tin nhan cho Duy
- Lap lai moi 15 phut cho den khi nop_tien done hoac order bi xoa
"""

import asyncio
import logging

from order_db import get_order_by_thread_id, _get_connection
from server_app import state

log = logging.getLogger("nop_tien_reminder")

# Tranh start nhieu timer cho cung 1 order
_active: set[int] = set()


def start_reminder(thread_id: int):
    """Goi khi giao hang done. Start background loop reminder."""
    if thread_id in _active:
        log.debug("reminder already active for order %d", thread_id)
        return
    _active.add(thread_id)
    asyncio.create_task(_reminder_loop(thread_id), name=f"nop_tien_reminder_{thread_id}")


async def _reminder_loop(thread_id: int):
    """Check moi 15 phut. Gui tin nhan cho Duy neu nop_tien chua done."""
    try:
        while True:
            await asyncio.sleep(15 * 60)

            conn = _get_connection()
            order = get_order_by_thread_id(conn, thread_id)
            if not order:
                log.info("order %d deleted — stop reminder", thread_id)
                return

            task_status = order.get("task_status", {}) or {}
            nop = task_status.get("nop_tien", {})
            if nop.get("done") or nop.get("skip"):
                log.info("order %d: nop_tien done — stop reminder", thread_id)
                return

            duy_id = state.duy_user_id
            if not duy_id:
                log.warning("duy_user_id not set — skip reminder order=%d", thread_id)
                return

            customer = order.get("khach_hang", order.get("name", "?"))
            text = (order.get("text") or order.get("text_raw") or "")[:80]

            try:
                await state._client.send_message(
                    duy_id,
                    f"⏰ Nhac nop tien!\n"
                    f"Don hang #{thread_id}\n"
                    f"Khach: {customer}\n"
                    f"Noi dung: {text}\n"
                    f"Da giao hang nhung chua nop tien sau 15 phut!"
                )
                log.info("sent reminder to Duy for order %d", thread_id)
            except Exception as e:
                log.error("failed send reminder order %d: %s", thread_id, e)
    finally:
        _active.discard(thread_id)
