"""Dashboard LỢI NHUẬN — lõi tính toán cho UI native của webapp (#/loi-nhuan).

Port từ repo anh em `profit-dashboard` (app 8091, legacy); bộ trang HTML
server-render /loi-nhuan/* đã GỠ 2026-08-26 — UI giờ là các trang Preact của
webapp, API = server_app/profit_api_routes.py (/api/profit/*, CHỈ VĂN PHÒNG).
Module: compute.py (số liệu dashboard/khách/SP) · queries.py (feed đơn + freeze
giá vốn) · settings.py (tiền vay + trọng số tháng, file JSON) · utils.py
(tên khách + phân bổ tiền vay). Nói chuyện với: order_store (blob orders),
product_store (calculate_order_profit / upsert_product).
"""
