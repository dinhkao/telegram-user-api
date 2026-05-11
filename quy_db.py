"""quy_db.py — Fund receipt creation + fund group notification.

Mirrors the fund receipt logic from Node.js processCashPaymentForOrder().
Only used for 'tm' (cash) payments — NOT for 'ck' (transfer).
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone, timedelta

from firebase_sync import set_fund_receipt, get_fund_receipts

log = logging.getLogger("quy_db")

FUND_GROUP_ID = int(os.getenv("FUND_GROUP_ID", "-1002420020918"))


def create_fund_receipt(
    amount: int,
    khach_hang_name: str,
    created_by: str,
    client=None,
    order_chat_id: int | None = None,
    order_thread_id: int | None = None,
) -> dict | None:
    """Create a fund receipt (phiếu thu quỹ) and notify fund group.
    
    Returns the receipt dict on success, or None on failure.
    Only called for 'tm' (cash) payments.
    """
    receipt_id = str(int(datetime.now(timezone.utc).timestamp() * 1000))
    today = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")

    receipt = {
        "id": receipt_id,
        "type": "thu",
        "amount": amount,
        "reason": f"Thanh toán tiền mặt đơn hàng - {khach_hang_name}",
        "source": "don_hang",
        "createdBy": created_by,
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "date": today,
    }

    ok = set_fund_receipt(receipt_id, receipt)
    if not ok:
        log.warning("Fund receipt write failed (Firebase not configured?)")
        # Still try to notify fund group even without Firebase
    else:
        log.info("Fund receipt created: %s %s %dđ", receipt_id, receipt["type"], amount)

    # Notify fund group via Telegram
    if client and FUND_GROUP_ID:
        try:
            all_receipts = get_fund_receipts()
            today_total = 0
            for r in all_receipts.values():
                if r.get("date") == today:
                    today_total += r.get("amount", 0) if r.get("type") == "thu" else -r.get("amount", 0)

            # Vietnam time display
            vn_now = datetime.now(timezone(timedelta(hours=7)))
            vn_display = vn_now.strftime("%H:%M:%S %d/%m/%Y")

            note = (
                f"📋 PHIẾU THU QUỸ MỚI\n\n"
                f"💰 Loại: Phiếu THU\n"
                f"📊 Số tiền: +{amount:,}đ\n"
                f"📝 Lý do: {receipt['reason']}\n"
                f"🏪 Nguồn: Thanh toán đơn hàng\n"
                f"👤 Người tạo: {created_by}\n"
                f"⏰ Thời gian: {vn_display}\n\n"
                f"💼 Tổng quỹ hôm nay: {today_total:,}đ"
            )
            client.loop.create_task(
                client.send_message(FUND_GROUP_ID, note)
            )
        except Exception as e:
            log.warning("Failed to notify fund group: %s", e)

    # Notify order group that fund receipt was created
    if client and order_chat_id and order_thread_id:
        try:
            client.loop.create_task(
                client.send_message(
                    order_chat_id,
                    "✅ Đã tạo phiếu thu quỹ và thông báo vào group quỹ",
                    reply_to=order_thread_id,
                )
            )
        except Exception as e:
            log.warning("Failed to notify order group about fund receipt: %s", e)

    return receipt
