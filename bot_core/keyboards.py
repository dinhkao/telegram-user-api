"""bot_core/keyboards.py — Reply and inline keyboard builders."""
from telethon import Button

from bot_core.config import PRODUCT_CODE_ROWS, QTY_OPTIONS, QTY_OPTIONS_BY_CODE


def build_actions_keyboard(task_status: dict | None, user_id: int | None):
    """Mirror JS buildActionsKeyboard using Telethon Buttons."""
    ts = task_status or {}
    from bot_core.config import name_of_user_id

    def _label(key, base, own_clear, other_done_text):
        entry = ts.get(key) or {}
        if entry.get("done"):
            by = str(entry.get("by") or "").strip()
            is_self = by and str(user_id) == by
            who = name_of_user_id(by)
            if key == "ban_hd":
                return f"✅ {who}{other_done_text}" if who else f"✅ {other_done_text}"
            if is_self:
                return own_clear
            return f"✅ {who}{other_done_text}" if who else f"✅ {other_done_text}"
        return base

    row1 = [
        Button.text(_label("ban_hd", "Bán HD", "Huỷ bán", "đã bán")),
        Button.text(_label("soan_hang", "Soạn hàng", "Huỷ soạn", "đã soạn")),
        Button.text(_label("giao_hang", "Giao hàng", "Huỷ giao", "đã giao")),
    ]
    row2 = [
        Button.text(_label("nop_tien", "Nộp tiền", "Huỷ nộp", "đã nộp")),
        Button.text(_label("nhan_tien", "Nhận tiền", "Huỷ nhận", "đã nhận")),
    ]
    row3 = [
        Button.text("Xem hóa đơn"),
        Button.text("In hóa đơn giao"),
        Button.text("Tạo HD"),
    ]
    row4 = [
        Button.text("Xem thông tin"),
        Button.text("Xem khách hàng"),
        Button.text("Sửa tên đơn hàng"),
        Button.text("Hối"),
    ]
    return [row1, row2, row3, row4]


def build_codes_keyboard():
    if not PRODUCT_CODE_ROWS:
        return None
    return [[Button.text(c) for c in row] for row in PRODUCT_CODE_ROWS]


def build_qty_keyboard(code: str | None):
    opts = QTY_OPTIONS_BY_CODE.get(code) or QTY_OPTIONS
    rows = []
    for i in range(0, len(opts), 6):
        rows.append([Button.text(n) for n in opts[i : i + 6]])
    return rows


def build_confirm_keyboard():
    return [[Button.text("Có")], [Button.text("Không")]]


def build_kv_confirm_keyboard():
    return [
        [Button.text("Ok tạo, tôi đã kiểm tra kỹ")],
        [Button.text("Không, quay lại")],
    ]


def build_rename_keyboard():
    return [[Button.text("< Quay lại, không sửa nữa")]]


def build_inline_invoice_keyboard(has_items: bool = False, has_kv: bool = False):
    """Inline keyboard for show invoice message."""
    rows = [[Button.inline("Cập nhật hóa đơn", b"inv:edit")]]
    if has_items and not has_kv:
        rows.append([Button.inline("Tạo hóa đơn Kiotviet luôn!", b"kv:create")])
    return rows


# Re-export from keyboards_extra for backward compatibility
from bot_core.keyboards_extra import (
    build_payment_methods_keyboard,
    build_payment_amount_keyboard,
    build_nop_wizard_type_keyboard,
    build_nop_wizard_ky_toa_keyboard,
    build_invoice_next_keyboard,
    build_price_choice_keyboard,
)
