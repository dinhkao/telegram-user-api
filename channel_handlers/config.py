from __future__ import annotations

import os
import time

CHANNEL_DON_HANG_MOI = int(os.getenv("CHANNEL_DON_HANG_MOI", "-1002138495144"))
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))


def build_firebase_key(message_id: int) -> str:
    return f"dh_{message_id}"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())


def build_new_order(order_text: str, text_raw: str, thread_id: int, firebase_key: str, message_id: int) -> dict:
    task = {"done": False, "by": None, "at": None, "skip": False}
    now = now_iso()
    return {
        "text": order_text,
        "text_raw": text_raw,
        "done": False,
        "created": now,
        "updated_at": now,
        "thread_id": thread_id,
        "firebase_key": firebase_key,
        "channel_id": CHANNEL_DON_HANG_MOI,
        "message_id": message_id,
        "flow_version": 2,
        "task_status": {k: dict(task) for k in ("ban_hd", "soan_hang", "giao_hang", "nop_tien", "nhan_tien")},
        "soan": False,
        "giao": False,
        "nop": False,
        "nhan": False,
    }
