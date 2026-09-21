# So sánh bản gốc và lãi hiện tại

Đối chiếu trên cùng snapshot SQLite chỉ đọc lúc 2026-09-10T19:14:51.836517+07:00. Bản gốc là code trước
mọi sửa toán (commit 21a3b8b8140b87c6db13541304a6237c02b9594a), không phải bản tạm đã loại VAT. Cột hiện tại đã
khôi phục VAT thu khách theo quy ước vốn đã gồm VAT bán ra dự tính.

Đơn vị: đồng. Chênh lệch lãi gộp bằng chênh lệch lãi sau lãi vay vì cùng cấu hình
và cùng số ngày phân bổ lãi vay. Chưa trừ hết các chi phí vận hành khác.

| Kỳ | Lãi gộp gốc | Lãi gộp hiện tại | Sau lãi vay gốc | Sau lãi vay hiện tại | Chênh lệch |
|---|---:|---:|---:|---:|---:|
| 2026-09-01 → 2026-09-10 | 64.003.164 | 64.003.164 | 47.128.164 | 47.128.164 | 0 |
| 2026-08-12 → 2026-09-10 | 192.109.093 | 190.723.093 | 142.572.803 | 141.186.803 | -1.386.000 |
| 2026-01-01 → 2026-09-10 | 714.045.994 | 707.032.170 | 190.920.994 | 183.907.170 | -7.013.824 |

## Nguyên nhân

- 01/09–10/09: không đổi cả lãi gộp lẫn lãi sau lãi vay. Doanh thu hiển thị mới loại VAT nhưng phép tính lãi đã cộng lại VAT thu khách đúng quy ước vốn; thay nhãn doanh thu không làm mất phần lãi này.
- 12/08–10/09: giảm đúng 1.386.000đ của phiếu trả đã xác nhận và hàng đã hủy; bản gốc bỏ qua phiếu trả.
- 01/01–10/09: giảm ròng 7.013.824đ, gồm:
  - −57.928.660đ: bỏ phần lãi tạm tính bằng giá vốn danh mục hiện tại ở 180 đơn chưa đủ vốn lịch sử được lưu.
  - +20.000đ: ghi nhận phí vận chuyển thu khách ở đơn #487991; bản gốc bỏ khoản này vì đơn chưa có vốn.
  - +52.720.836đ: phần lãi và điều chỉnh cấp đơn xác định từ 3.328 đơn trước mốc 460000 mới được đưa vào phạm vi.
  - −1.826.000đ: 3 phiếu trả đã xác nhận.

Tổng cầu nối: −57.928.660 + 20.000 + 52.720.836 − 1.826.000 = **−7.013.824đ**.

## Giới hạn khi đọc số

Cột hiện tại là **phần lãi đã xác định**, chưa phải lợi nhuận đầy đủ: kỳ tháng 9
còn 3 đơn thiếu giá vốn (4.410.000đ doanh thu); kỳ năm còn 3.523 đơn thiếu vốn
lịch sử (10.565.064.500đ doanh thu). Trong hệ thống có 7 đơn thiếu ngày tạo nên
chưa thể gán kỳ. Kỳ năm còn 1 phiếu trả chưa có kết quả xử lý hàng.

Đây là số toàn doanh nghiệp, không áp thêm bộ lọc. Khi lọc nhóm, bản hiện tại
chỉ hiển thị lãi gộp; bản gốc trừ toàn bộ lãi vay doanh nghiệp vào nhóm.

[Snapshot và cầu nối từng kỳ](profit_before_after_2026-09-10.json). Việc đối chiếu
không sửa dữ liệu, công thức hay khởi động lại server.
