"""Thông báo KHO ĐẬU — mỗi phiếu nhập / xuất / điều chỉnh đẩy 1 thông báo.

Nội dung dựng THUẦN ở `build_bean_notif` (không IO, unit-tested:
tests/test_bean_notify.py), gửi qua server_app.notify.push_bg → ghi trung tâm
thông báo trong app + push FCM. Không thuộc đơn hàng nên deep-link bằng
data['route'] = '#/kho-dau/phieu/<id>' (NotifCenter mở thẳng route đó).
Gọi từ: server_app.bean_slip_routes.
"""
from __future__ import annotations

import logging

from bean_store.domain import KIND_LABELS, fmt_qty

log = logging.getLogger("bean_notify")

# Biểu tượng + tiêu đề theo loại phiếu. Tiêu đề viết riêng ở đây (không ghép
# KIND_LABELS + "đậu": ra "Điều chỉnh đậu", đọc như đang chỉnh hạt đậu).
KIND_ICONS = {"nhap": "📥", "xuat": "📤", "dieu_chinh": "⚖️"}
KIND_TITLES = {"nhap": "Nhập kho đậu", "xuat": "Xuất kho đậu",
               "dieu_chinh": "Điều chỉnh kho đậu"}

_MAX_LINES = 3   # phiếu dài → cắt bớt, phần dư gộp "+ N dòng nữa"


def _line(kind: str, it: dict) -> str:
    """1 dòng đậu cho người đọc.

    nhập/xuất → ĐÚNG thứ người dùng gõ ("3 bao"); điều chỉnh → số ĐẾM + chênh lệch
    theo ĐƠN VỊ GỐC (delta luôn tính bằng đơn vị gốc, ghép với số bao là sai nghĩa).
    """
    name = str(it.get("bean_name") or "").strip() or "?"
    base_unit = str(it.get("unit") or "").strip()
    if kind == "dieu_chinh":
        qty = fmt_qty(float(it.get("quantity") or 0))
        delta = float(it.get("delta") or 0)
        tail = " (không đổi)" if not delta else \
            f" ({'+' if delta > 0 else '−'}{fmt_qty(abs(delta))}{' ' + base_unit if base_unit else ''})"
        return f"{name} {qty}{' ' + base_unit if base_unit else ''}{tail}"
    unit = str(it.get("entered_unit") or base_unit).strip()
    qty = fmt_qty(float(it.get("entered_qty") if it.get("entered_qty") is not None
                        else it.get("quantity") or 0))
    return f"{name} {qty}{' ' + unit if unit else ''}"


def build_bean_notif(slip: dict, actor: str = "") -> tuple[str, str, dict]:
    """(title, body, data) cho 1 phiếu kho đậu vừa tạo."""
    kind = str(slip.get("kind") or "")
    label = KIND_TITLES.get(kind) or f"{KIND_LABELS.get(kind, 'Phiếu')} kho đậu"
    title = f"{KIND_ICONS.get(kind, '🫘')} {label}"

    items = [i for i in (slip.get("items") or []) if isinstance(i, dict)]
    lines = [_line(kind, i) for i in items[:_MAX_LINES]]
    if len(items) > _MAX_LINES:
        lines.append(f"+{len(items) - _MAX_LINES} dòng nữa")

    head = " · ".join(x for x in (str(actor or "").strip(),
                                  str(slip.get("place_name") or "").strip()) if x)
    body = f"{head}: {', '.join(lines)}" if head else ", ".join(lines)
    partner = str(slip.get("partner") or "").strip()
    if partner:
        body += f" ({partner})"
    return title, body[:200], {"type": "bean_slip", "route": f"#/kho-dau/phieu/{slip.get('id')}"}


def notify_bean_slip(slip: dict, actor: str = "") -> None:
    """Đẩy thông báo phiếu kho đậu (best-effort — lỗi không được làm hỏng việc tạo phiếu)."""
    try:
        title, body, data = build_bean_notif(slip, actor)
        from server_app.notify import push_bg
        push_bg(title, body, data)
    except Exception as e:  # noqa: BLE001
        log.warning("Thông báo phiếu kho đậu lỗi: %s", e)
