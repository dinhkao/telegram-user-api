"""bot_don_hang/flows/payment.py — Nhận tiền payment flow."""
from telethon import Button

from bot_core import config, db, keyboards
from bot_core.utils import post_json, is_cancel
from bot_core.store import reset_timer
from ._helpers import log, USER_API_BASE, _nf


async def start_payment_flow(bot, event, s):
    """Start Nhận tiền payment flow with amount suggestion."""
    if not config.is_admin(s.user_id):
        await event.reply("Chức năng chỉ dành cho admin (Duy, Trang).")
        return
    if not s.thread_id:
        await event.reply(f"Không lấy được thread_id cho đơn {s.order_id}.")
        return
    # Fetch totals to suggest the order amount
    suggested = None
    try:
        totals = await post_json(f"{USER_API_BASE}/api/order/totals", {
            "thread_id": s.thread_id,
            "use_initial_debt": False,
        })
        if totals and totals.get("order") and isinstance(totals["order"].get("pre_debt_total"), (int, float)):
            suggested = int(totals["order"]["pre_debt_total"])
        elif isinstance(totals.get("pre_debt_total"), (int, float)):
            suggested = int(totals["pre_debt_total"])
        elif isinstance(totals.get("total_payable"), (int, float)):
            suggested = int(totals["total_payable"])
    except Exception as e:
        log.warning("totals fetch failed: %s", e)

    s.pay_flow = {"active": True, "step": "ask_amount", "suggested": suggested, "amount": None}
    rows = []
    if suggested:
        rows.append([Button.text(f"Dùng số tiền gợi ý {_nf(suggested)}")])
    rows.append([Button.text("Huỷ")])
    await event.reply(
        f"Nhập số tiền khách thanh toán. Gợi ý: {_nf(suggested)} VND" if suggested else "Nhập số tiền khách thanh toán.",
        buttons=rows,
    )
    reset_timer(s.chat_id)


async def handle_payment_text(bot, event, s, text):
    """Handle text input during payment flow."""
    pf = s.pay_flow
    if not pf or not pf.get("active"):
        return
    txt = text.strip().lower()
    nf = _nf

    if is_cancel(text):
        s.pay_flow = None
        from bot_core.handlers import send_help
        await send_help(bot, s.chat_id, s)
        return

    if pf.get("step") == "ask_amount":
        amt = None
        if txt.startswith("dùng số tiền"):
            amt = pf.get("suggested")
        else:
            cleaned = "".join(c for c in text if c.isdigit())
            if cleaned:
                val = int(cleaned)
                if val > 0:
                    amt = val
        if amt and amt > 0:
            pf["amount"] = amt
            pf["step"] = "ask_method"
            await event.reply(
                f"Số tiền: {nf(amt)}. Chọn phương thức thanh toán:",
                buttons=keyboards.build_payment_methods_keyboard(),
            )
            return
        suggested = pf.get("suggested")
        rows = []
        if suggested:
            rows.append([Button.text(f"Dùng số tiền gợi ý {nf(suggested)}")])
        rows.append([Button.text("Huỷ")])
        await event.reply("Số tiền không hợp lệ. Nhập số tiền hoặc chọn gợi ý.", buttons=rows)
        return

    if pf.get("step") == "ask_method":
        is_tm = txt == "tiền mặt"
        is_ck = txt in ("chuyển khoản", "chuyen khoan")
        if not is_tm and not is_ck:
            await event.reply("Hãy chọn phương thức: Tiền mặt hoặc Chuyển khoản.",
                buttons=keyboards.build_payment_methods_keyboard())
            return
        thread_id = s.thread_id
        if not thread_id:
            s.pay_flow = None
            await event.reply(f"Không lấy được thread_id cho đơn {s.order_id}.")
            return
        method = "tm" if is_tm else "ck"
        amt = int(pf.get("amount", 0))
        try:
            await event.reply(f"Đang tạo thanh toán {'tiền mặt' if is_tm else 'chuyển khoản'}: {nf(amt)}...")
            resp = await post_json(f"{USER_API_BASE}/api/order/payment/{method}", {
                "thread_id": thread_id,
                "amount": amt,
                "user_id": s.user_id,
            })
            debt_note = ""
            if resp and isinstance(resp.get("new_debt"), (int, float)):
                debt_note = f" • Nợ mới: {nf(resp['new_debt'])}"
            caption = f"Đã nhận {nf(amt)} ({'tiền mặt' if is_tm else 'chuyển khoản'}){debt_note}"
            # Refresh
            try:
                fresh = db.get_order(s.order_id)
                if fresh:
                    s.task_status = fresh.get("task_status")
            except Exception:
                pass
            from bot_core.handlers import send_help
            await send_help(bot, s.chat_id, s)
            await event.reply(caption)
        except Exception as e:
            log.error("payment error: %s", e)
            await event.reply(f"Tạo thanh toán thất bại: {e}")
        finally:
            s.pay_flow = None
            reset_timer(s.chat_id)
