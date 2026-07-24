"""KHOÁ THANH TOÁN toàn cục — serialize mọi đường tạo phiếu thu (web bulk /
#/thu-tien-nhanh batch / Telegram `tm`) để đóng khe TOCTOU quanh 2 round-trip
KiotViet: validate-còn-thiếu → tạo phiếu KV → ghi local phải là 1 khối, không
cho 2 thanh toán cùng khách/đơn lồng nhau (2 máy bấm gần nhau = thu ĐÔI tiền,
tiền thừa còn bị hệ két materialize ra từ hư không).

Cùng vai với `_invoice_create_lock` (order_commands_v3) bên nhánh hoá đơn.
Giữ khoá qua await KiotViet là CHỦ ĐÍCH: thanh toán ít (5-6 người dùng), đúng
quan trọng hơn nhanh. Leaf module — chỉ asyncio.
"""
import asyncio

# 1 khoá cho MỌI thanh toán (không per-order: bulk đụng N đơn 1 lúc, khoá đơn
# lẻ sẽ phải sort-and-lock N khoá — không đáng với tần suất hiện tại).
payment_lock = asyncio.Lock()
