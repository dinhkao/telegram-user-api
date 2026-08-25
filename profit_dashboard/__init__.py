"""profit_dashboard — dashboard LỢI NHUẬN (port từ repo profit-dashboard 2026-08-25).

Trang HTML server-render (tailwind CDN + alpinejs) tính lợi nhuận đơn/SP/khách từ
blob orders + giá vốn product_store. Mount dưới prefix /loi-nhuan trên server chính
(server_app/profit_routes.py), CHỈ VĂN PHÒNG. Nói chuyện với: order_store,
product_store (calculate_order_profit), bot_core.config (USER_NAMES).
"""
from __future__ import annotations

from profit_dashboard.settings import load_settings, save_settings, DEFAULT_WEIGHTS  # noqa: F401
