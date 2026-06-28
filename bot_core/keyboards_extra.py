"""bot_core/keyboards_extra.py — Extra keyboard builders (payment, nop wizard, invoice edit)."""
from telethon import Button


def build_payment_methods_keyboard():
    return [
        [Button.text("Tiền mặt"), Button.text("Chuyển khoản")],
        [Button.text("Huỷ")],
    ]


def build_payment_amount_keyboard(suggested: int | None = None):
    rows = []
    if suggested:
        rows.append([Button.text(f"Dùng số tiền gợi ý {suggested:,}")])
    rows.append([Button.text("Huỷ")])
    return rows


def build_nop_wizard_type_keyboard():
    return [
        [Button.text("Báo khách nợ"), Button.text("Báo khách trả đủ")],
        [Button.text("Huỷ")],
    ]


def build_nop_wizard_ky_toa_keyboard():
    return [
        [Button.text("Có ký toa"), Button.text("Không ký toa"), Button.text("Chiều lấy tiền")],
        [Button.text("Huỷ")],
    ]


def build_invoice_next_keyboard():
    return [
        [Button.text("Thêm dòng mới"), Button.text("Hoàn tất")],
        [Button.text("Huỷ")],
    ]


def build_price_choice_keyboard(suggested_price: int | None = None):
    rows = []
    if suggested_price is not None:
        rows.append([Button.text(f"Dùng giá có sẵn {suggested_price}")])
    rows.append([Button.text("Tự nhập giá")])
    rows.append([Button.text("Huỷ")])
    return rows
