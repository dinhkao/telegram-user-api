# Điều chỉnh VAT theo quy ước giá vốn đã xác nhận

Người dùng xác nhận: **giá vốn đã tính sẵn khoản VAT bán ra phải chịu**.
Đây không phải VAT mua vào. Việc bỏ VAT thu khách khỏi lãi trong lần sửa đầu
là không phù hợp với cách nhập vốn này; kết luận trước đó về lỗi VAT được rút lại.

## Công thức đã triển khai

Với đơn đủ vốn:

**Lãi quản trị = tiền hàng + VAT bán ra thu khách + phí vận chuyển thu khách − chiết khấu − giá vốn đã gồm VAT dự tính − chi phí giao hàng đã ghi.**

Ví dụ: vốn nhập 108 = vốn sản xuất 100 + VAT dự tính 8; tiền hàng 150, VAT thu
khách 8. Tổng tiền khách trả 158; lãi = 158 − 108 = **50**. Bỏ VAT thu khách
sẽ cho 42, làm giảm lãi 8 so với quy ước này.

- Doanh thu báo cáo vẫn là doanh thu chưa VAT; tổng tiền khách thanh toán có VAT. Biên lãi dùng doanh thu chưa VAT làm mẫu số.
- Không tự tách 8% khỏi giá vốn hoặc đoán số VAT dự tính trong từng sản phẩm. Nếu không thu VAT trên đơn thì không tự cộng một khoản VAT giả định.
- VAT thu khách được cộng một lần ở cấp đơn. Lãi dòng SP chưa phân bổ VAT/phí cấp đơn và được ghi rõ trên UI. Tổng đơn/khách/chart đã có điều chỉnh này.
- Đơn thiếu vốn vẫn chỉ có phần lãi xác định và các khoản điều chỉnh cấp đơn, chưa phải lãi đầy đủ.
- Giữ các sửa khác: phạm vi lịch sử, phiếu trả, đếm đơn phân biệt, danh tính SP, ẩn lãi vay ở nhóm lọc, cảnh báo dữ liệu.
- Đây là phép tính quản trị theo vốn người dùng nhập; không xác minh lại số VAT dự tính trong vốn hay làm tờ khai thuế.

## Đối chiếu chỉ đọc

Snapshot: 2026-09-10T19:07:05.722538+07:00. So với bản loại VAT trước đó, phần lãi xác định tăng đúng số
VAT thu khách trong cùng tập đơn. Các tổng khớp phép tính độc lập từ JSON,
biểu đồ và tổng khách hàng; sai lệch 0 đồng.

| Kỳ | VAT thu khách (đ) | Phần lãi xác định (đ) | Sau lãi vay (đ) |
|---|---:|---:|---:|
| 2026-09-01 → 2026-09-10 | 2.254.720 | 64.003.164 | 47.128.164 |
| 2026-08-12 → 2026-09-10 | 9.588.240 | 190.723.093 | 141.186.803 |
| 2026-01-01 → 2026-09-10 | 95.122.476 | 707.032.170 | 183.907.170 |

Các số trên vẫn chịu cảnh báo thiếu giá vốn/ngày đã nêu trong audit; chưa dùng
làm kết luận tổng lãi/lỗ khi dữ liệu còn thiếu.

## Kiểm tra

- 60 tests lợi nhuận đạt; 11 kiểm tra audit đạt; TypeScript đạt.
- Chrome: đơn có VAT 8.000, giá vốn đã dự tính VAT; tổng khách trả 108.000 và lãi 48.000 khớp API. UI ghi rõ VAT và phạm vi lãi SP; không tràn ở 320/390/1280px, không lỗi JavaScript.
- [Snapshot số liệu](profit_math_vat_confirmed_2026-09-10.json).
- Chạy lại đối chiếu: `.venv/bin/python docs/audits/reconcile_profit_math.py`.

Không sửa dữ liệu đơn hàng hay giá vốn thật; chỉ thay công thức, nhãn giải thích và kiểm thử.

## Trạng thái triển khai

Đã cập nhật lúc 2026-09-10T19:11:02+07:00.
Server PID 43703 đang nghe cổng 8090. /app/ và asset mới HTTP 200,
khớp byte với bản build đã kiểm tra; API lợi nhuận chưa đăng nhập HTTP 403.
Không có traceback khởi động. Toàn bộ build/asset được chuẩn bị trước khi nạp
lại server; index.html thay nguyên tử trên cùng ổ đĩa.
