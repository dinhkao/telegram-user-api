"""bot_flows/invoice_edit.py — Edit invoice line items with price flow."""
import asyncio

from telethon import Button

from bot_core import config, keyboards
from bot_core.utils import post_json, is_cancel
from bot_core.store import reset_timer
from ._helpers import log, ORDER_API_BASE


async def handle_invoice_edit_text(bot, event, s, text):
    """Handle text input during invoice editing."""
    state = s.edit_invoice
    if not state:
        return
    step = state.get("step")

    if is_cancel(text):
        s.edit_invoice = None
        from bot_handlers import send_help
        await send_help(bot, s.chat_id, s)
        return

    if step == "choose_code":
        code = text.upper().strip()
        if code not in config.PRODUCT_CODES and not (len(code) >= 2 and code.replace("-", "").replace("_", "").isalnum()):
            await event.reply("Mã sản phẩm không hợp lệ.")
            return
        state["current_code"] = code
        state["step"] = "choose_qty"
        kb = keyboards.build_qty_keyboard(code)
        await event.reply(f"Nhập hoặc chọn số lượng cho {code}:", buttons=kb + [[Button.text("Huỷ")]])
        state["suggested_price"] = None
        state["suggested_source"] = None
        async def _lookup():
            try:
                resp = await post_json(f"{ORDER_API_BASE}/api/customer/price", {"customer_id": s.customer_id, "product": code})
                if resp and resp.get("ok") and state.get("active") and state.get("current_code") == code:
                    state["suggested_price"] = resp.get("price")
                    state["suggested_source"] = resp.get("source")
            except Exception:
                pass
        asyncio.create_task(_lookup())
        return

    if step == "choose_qty":
        qty_text = text.strip()
        qty_num = int(qty_text) if qty_text.isdigit() else None
        code = state.get("current_code")
        if not code:
            return
        if not (qty_num and qty_num > 0 and qty_num <= 1000000):
            await event.reply("Số lượng không hợp lệ.", buttons=keyboards.build_qty_keyboard(code) + [[Button.text("Huỷ")]])
            return
        state["current_qty"] = qty_num
        state["step"] = "choose_price"
        sp = state.get("suggested_price")
        if sp is not None:
            await event.reply(f"Chọn giá bán cho {code} (SL {qty_num}):",
                buttons=keyboards.build_price_choice_keyboard(sp))
        else:
            await event.reply(f"Khách hàng {s.customer_name or s.customer_id} chưa có giá cho {code}, hãy tự nhập",
                buttons=keyboards.build_price_choice_keyboard())
        return

    if step == "choose_price":
        from bot_flows.invoice_edit_finish import handle_choose_price
        await handle_choose_price(bot, event, s, state, text)
        return

    if step == "next_action":
        from bot_flows.invoice_edit_finish import handle_next_action
        await handle_next_action(bot, event, s, state, text)
