"""Fund (quỹ) group bot — ported from node bots/groupQuy.js.

Handles manual THU/CHI (money in/out) receipts typed directly into the fund
group chat. Reuses the existing telethon fund receipt store (quy_db /
firebase_sync funds) — no new SQLite table is introduced.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta

from telethon import events
from telethon.tl.types import MessageService

from firebase_sync import set_fund_receipt, get_fund_receipts
from quy_db import FUND_GROUP_ID

log = logging.getLogger("quy_commands")

_VN_TZ = timezone(timedelta(hours=7))
_AMOUNT_REASON_RE = re.compile(r"^([+-]?\d+)\s+(.+)$")

HELP_TEXT = """*DANH SÁCH LỆNH TRONG GROUP QUỸ*

*Tạo phiếu thu/chi:*
- `+<số tiền> <lý do>` hoặc `<số tiền> <lý do>`: Tạo phiếu THU (tiền vào).
- `-<số tiền> <lý do>`: Tạo phiếu CHI (tiền ra).
  - *Ví dụ thu:* `+500000 thu tiền hàng` hoặc `500000 thu tiền hàng`
  - *Ví dụ chi:* `-200000 chi phí vận chuyển`"""


def _so(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def _sender_full_name(sender) -> str:
    first = getattr(sender, "first_name", None) or ""
    last = getattr(sender, "last_name", None) or ""
    return f"{first} {last}".strip() if last else first


def register_quy_commands(client):
    log.info("quy handler listening on group %d", FUND_GROUP_ID)

    async def reply(msg, text, parse_mode=None):
        await client.send_message(msg.chat_id, text, reply_to=msg.id, parse_mode=parse_mode)

    @client.on(events.NewMessage(chats=FUND_GROUP_ID))
    async def on_group_msg(event):
        msg = event.message
        if isinstance(msg, MessageService) or not msg.text:
            return
        text = msg.text.strip()

        if text == "?":
            await reply(msg, HELP_TEXT, parse_mode="md")
            return

        if not re.match(r"^[+-]?\d+\s+.+", text):
            return

        match = _AMOUNT_REASON_RE.match(text)
        if not match:
            return

        try:
            amount = int(match.group(1))
        except ValueError:
            return
        reason = match.group(2).strip()

        sender = await event.get_sender()
        created_by = _sender_full_name(sender)

        now_utc = datetime.now(timezone.utc)
        now_vn = datetime.now(_VN_TZ)
        receipt_id = str(int(now_utc.timestamp() * 1000))
        receipt_type = "thu" if amount > 0 else "chi"
        receipt = {
            "id": receipt_id,
            "type": receipt_type,
            "amount": abs(amount),
            "reason": reason,
            "source": "manual",
            "createdBy": created_by,
            "createdAt": now_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "date": now_vn.strftime("%Y-%m-%d"),
        }

        try:
            set_fund_receipt(receipt_id, receipt)
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to save fund receipt: %s", e)

        today = now_vn.strftime("%Y-%m-%d")
        today_total = 0
        try:
            all_receipts = get_fund_receipts() or {}
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to fetch fund receipts: %s", e)
            all_receipts = {}
        for r in all_receipts.values():
            if r.get("date") == today:
                today_total += r.get("amount", 0) if r.get("type") == "thu" else -r.get("amount", 0)

        sign = "+" if amount > 0 else "-"
        receipt_label = "THU" if amount > 0 else "CHI"
        vn_display = now_vn.strftime("%H:%M:%S %d/%m/%Y")

        notification = (
            f"📋 PHIẾU {receipt_label} QUỸ MỚI\n\n"
            f"💰 Loại: Phiếu {receipt_label}\n"
            f"📊 Số tiền: {sign}{_so(abs(amount))}đ\n"
            f"📝 Lý do: {reason}\n"
            f"🏪 Nguồn: Tạo thủ công\n"
            f"👤 Người tạo: {created_by}\n"
            f"⏰ Thời gian: {vn_display}\n\n"
            f"💼 Tổng quỹ hôm nay: {_so(today_total)}đ"
        )

        await client.send_message(FUND_GROUP_ID, notification)
