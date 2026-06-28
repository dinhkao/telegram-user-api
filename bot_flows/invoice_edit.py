"""bot_don_hang/flows/invoice_edit.py — Edit invoice line items with price flow."""
import asyncio

from telethon import Button

from bot_core import config, keyboards
from bot_core.utils import post_json, is_cancel
from bot_core.store import reset_timer
from ._helpers import log, ORDER_API_BASE, _nf
from .invoice_show import handle_show_invoice


async def handle_invoice_edit_text(bot, event, s, text):
    """Handle text input during invoice editing."""
    state = s.edit_invoice
    if not state:
        return
    step = state.get("step")

    if is_cancel(text):
        s.edit_invoice = None
        from bot_core.handlers import send_help
        await send_help(bot, s.chat_id, s)
        return

    if step == "choose_code":
        code = text.upper().strip()
        # Allow any code matching basic pattern, or from hardcoded list
        if code not in config.PRODUCT_CODES and not (len(code) >= 2 and code.replace("-", "").replace("_", "").isalnum()):
            await event.reply("Mã sản phẩm không hợp lệ. Chọn hoặc gõ mã trong danh sách.")
            return
        state["current_code"] = code
        state["step"] = "choose_qty"
        kb = keyboards.build_qty_keyboard(code)
        await event.reply(f"Nhập hoặc chọn số lượng cho {code}:", buttons=kb + [[Button.text("Huỷ")]])
        # Trigger suggested price lookup in background
        state["suggested_price"] = None
        state["suggested_source"] = None
        async def _lookup():
            try:
                cust_id = s.customer_id
                if not cust_id:
                    return
                resp = await post_json(f"{ORDER_API_BASE}/api/customer/price", {"customer_id": cust_id, "product": code})
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
        valid = qty_num and qty_num > 0 and qty_num <= 1000000
        if not valid:
            await event.reply("Số lượng không hợp lệ. Hãy gõ số hoặc chọn gợi ý.",
                buttons=keyboards.build_qty_keyboard(code) + [[Button.text("Huỷ")]])
            return
        state["current_qty"] = qty_num
        state["step"] = "choose_price"
        cust_name = s.customer_name or s.customer_id or ""
        sp = state.get("suggested_price")
        if sp is not None:
            await event.reply(f"Chọn giá bán cho {code} (SL {qty_num}):",
                buttons=keyboards.build_price_choice_keyboard(sp))
        else:
            await event.reply(f"Khách hàng {cust_name} chưa được thiết lập giá cho sản phẩm {code}, hãy tự nhập giá bán",
                buttons=keyboards.build_price_choice_keyboard())
        return

    if step == "choose_price":
        price_num = None
        raw = text.strip().lower()
        if raw.startswith("dùng giá có sẵn"):
            if state.get("suggested_price") is not None:
                price_num = int(state["suggested_price"])
        elif raw == "tự nhập giá":
            # Ignore, expect next message with number
            pass
        else:
            parsed = int(raw.replace("[^0-9]", "")) if raw.replace("[^0-9]", "").isdigit() else None
            if parsed and parsed > 0:
                price_num = parsed

        if price_num is not None and state.get("current_code") and state.get("current_qty"):
            draft = state.get("draft", [])
            draft.append({"sp": state["current_code"], "sl": state["current_qty"], "price": price_num})
            state["draft"] = draft
            preview_lines = [f"{it['sp']} = {it['sl']} x {it['price']}" for it in draft]
            preview_text = "\n".join(preview_lines)
            state["current_code"] = None
            state["current_qty"] = None
            state["suggested_price"] = None
            state["step"] = "next_action"
            msg = f"Đã thêm.\n\nHoá đơn hiện tại:\n{preview_text}\n\nChọn thao tác:"
            await event.reply(msg, buttons=keyboards.build_invoice_next_keyboard())
            return

        # Re-prompt
        code = state.get("current_code") or ""
        qty = state.get("current_qty") or ""
        sp = state.get("suggested_price")
        await event.reply(f"Hãy nhập giá bán cho {code} (SL {qty}).",
            buttons=keyboards.build_price_choice_keyboard(sp))
        return

    if step == "next_action":
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
            total = 0
            lines = []
            for item in draft:
                qty = int(item.get("sl", 0))
                price = int(item.get("price", 0))
                line_total = qty * price
                if price > 0:
                    total += line_total
                    lines.append(f"{item['sp']} = {_nf(qty)} x {_nf(price)} = {_nf(line_total)}")
                else:
                    lines.append(f"{item['sp']} = {_nf(qty)} (chưa có giá)")
            out = "\n".join(lines) if lines else "Hoá đơn trống."
            # Build follow-up keyboard (same as old bot)
            follow_up_kb = None
            if not s.kv_invoice_id and draft:
                follow_up_kb = [
                    [Button.text("Tạo hóa đơn Kiotviet luôn!")],
                    [Button.text("Quay lại")],
                ]
            # Update invoice items to backend
            try:
                thread_id = s.thread_id
                if thread_id:
                    items = [
                        {"sp": str(it["sp"]), "sl": int(it["sl"]), "price": int(it["price"]) if it.get("price") else None}
                        for it in draft
                        if it and isinstance(it, dict) and it.get("sp") and int(it.get("sl", 0)) > 0
                    ]
                    await post_json(f"{ORDER_API_BASE}/api/order/invoice/update", {
                        "thread_id": thread_id,
                        "user_id": s.user_id,
                        "invoice": items,
                    })
                    # Refresh local invoice cache from DB
                    try:
                        from bot_core import db
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
                    # After updating, show local invoice (fast, no API call)
                    await handle_show_invoice(bot, event, s)
                else:
                    await event.reply("Không lấy được thread_id để cập nhật hoá đơn.")
            except Exception as err:
                log.error("invoice/update error: %s", err)
                await event.reply(f"Cập nhật hoá đơn thất bại: {err}")
            state["active"] = False
            state["step"] = "idle"
            reset_timer(s.chat_id)
            return
        # If neither, ignore and re-prompt
        await event.reply('Chọn "Thêm dòng mới" hoặc "Hoàn tất".', buttons=keyboards.build_invoice_next_keyboard())
