from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

CHANNEL_DON_HANG_MOI = int(os.getenv("CHANNEL_DON_HANG_MOI", "-1002138495144"))
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))

# Giờ Việt Nam (UTC+7) — dùng cho mốc "giao trong ngày / dời sang mai" khi tạo đơn.
VN_TZ = timezone(timedelta(hours=7))


def build_firebase_key(message_id: int) -> str:
    return f"dh_{message_id}"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())


def default_ngay_giao(now: datetime | None = None) -> str:
    """Ngày giao mặc định khi tạo đơn = ngày tạo (giờ VN); tạo SAU 17:30 → dời sang mai.
    Trả chuỗi 'YYYY-MM-DDT00:00' (khớp input datetime-local; giờ 00:00 = chỉ tính ngày)."""
    now = now or datetime.now(VN_TZ)
    d = now.date()
    if (now.hour, now.minute) >= (17, 30):
        d = d + timedelta(days=1)
    return d.strftime("%Y-%m-%dT00:00")


def build_new_order(order_text: str, text_raw: str, thread_id: int, firebase_key: str, message_id: int) -> dict:
    task = {"done": False, "by": None, "at": None, "skip": False}
    now = now_iso()
    return {
        "text": order_text,
        "text_raw": text_raw,
        "done": False,
        "created": now,
        "updated_at": now,
        "ngay_giao": default_ngay_giao(),
        "ngay_giao_auto": True,   # đánh dấu do hệ tự đặt (chưa ai sửa tay)
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
