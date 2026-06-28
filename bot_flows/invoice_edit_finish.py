"""bot_flows/invoice_edit_finish.py — Invoice edit: price selection & completion."""
import logging
from telethon import Button
from bot_core import config, db, keyboards
from bot_core.utils import post_json
from bot_core.store import reset_timer
from ._helpers import log, ORDER_API_BASE, _nf
from .invoice_show import handle_show_invoice

async def handle_choose_price(bot, event, s, state, text):
    price_num = None
    raw = text.strip().lower()
    if raw.startswith("dùng giá có sẵn"):
        if state.get("suggested_price") is not None:
            price_num = int(state["suggested_price"])
    elif raw == "tự nhập giá":
        pass
    else:
        cleaned = "".join(c for c in raw if c.isdigit())
        if cleaned:
            parsed = int(cleaned)
            if parsed > 0:
                price_num = parsed
    if price_num is not None and state.get("current_code") and state.get("current_qty"):
        draft = state.get("draft", [])
        draft.append({"sp": state["current_code"], "sl": state["current_qty"], "price": price_num})
        state["draft"] = draft
        preview = "\n".join(f"{it['sp']} = {it['sl']} x {it['price']}" for it in draft)
        state["current_code"] = state["current_qty"] = state["suggested_price"] = None
        state["step"] = "next_action"
        await event.reply(f"Đã thêm.\n\nHoá đơn hiện tại:\n{preview}\n\nChọn thao tác:",
            buttons=keyboards.build_invoice_next_keyboard())
        return
    code, qty, sp = state.get("current_code") or "", state.get("current_qty") or "", state.get("suggested_price")
    await event.reply(f"Hãy nhập giá bán cho {code} (SL {qty}).",
        buttons=keyboards.build_price_choice_keyboard(sp))

async def handle_next_action(bot, event, s, state, text):
    t = text.strip().lower()
    if t == "thêm dòng mới":
        state["step"] = "choose_code"
        kb = keyboards.build_codes_keyboard()
        if kb:
            kb.append([Button.text("Huỷ")])
        await event.reply("Chọn mã sản phẩm:", buttons=kb)
        return
    if t == "hoàn tất":
        draft = state.get("draft", [])
        lines = []
        for item in draft:
            qty, price = int(item.get("sl", 0)), int(item.get("price", 0))
            total = qty * price
            lines.append(f"{item['sp']} = {_nf(qty)} x {_nf(price)} = {_nf(total)}" if price > 0
                else f"{item['sp']} = {_nf(qty)} (chưa có giá)")
        try:
            if s.thread_id:
                items = [{"sp": str(it["sp"]), "sl": int(it["sl"]), "price": int(it["price"]) if it.get("price") else None}
                    for it in draft if it and isinstance(it, dict) and it.get("sp") and int(it.get("sl", 0)) > 0]
                await post_json(f"{ORDER_API_BASE}/api/order/invoice/update", {
                    "thread_id": s.thread_id, "user_id": s.user_id, "invoice": items})
                try:
                    fresh = db.get_order(s.order_id)
                    if fresh:
                        s.invoice = fresh.get("invoice") or []
                        s.discount = int(fresh.get("discount", 0))
                        s.pvc = int(fresh.get("pvc", 0))
                        s.vat = int(fresh.get("vat", 0))
                        s.kh_debt = int(fresh.get("khDebt", 0))
                        s.payments = fresh.get("payments") or []
                except Exception:
                    pass
                await handle_show_invoice(bot, event, s)
            else:
                await event.reply("Không lấy được thread_id.")
        except Exception as err:
            log.error("invoice/update error: %s", err)
            await event.reply(f"Cập nhật hoá đơn thất bại: {err}")
        state["active"] = False
        state["step"] = "idle"
        reset_timer(s.chat_id)
        return
    await event.reply('Chọn "Thêm dòng mới" hoặc "Hoàn tất".', buttons=keyboards.build_invoice_next_keyboard())
