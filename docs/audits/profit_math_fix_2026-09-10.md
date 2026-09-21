# Sửa công thức báo cáo lợi nhuận — 10/09/2026

> **Đã chốt lại quy ước VAT:** Người dùng xác nhận giá vốn đã tính sẵn VAT **bán ra** phải chịu. Vì vậy việc loại VAT thu khách khỏi phép tính lãi trong bản sửa đầu là không phù hợp với quy ước này. Kết luận và số lãi của giai đoạn đó được thay thế bởi [bản điều chỉnh VAT đã xác nhận](profit_math_vat_confirmed_2026-09-10.md).

Đã sửa các lỗi đã xác định trong audit. Kết quả mới khớp phép tính độc lập trên
cùng snapshot SQLite chỉ đọc. Đây vẫn là báo cáo **phần lãi đã xác định** khi dữ
liệu thiếu giá vốn/ngày; không phải lợi nhuận kế toán đầy đủ.

## Thay đổi

- Bỏ giới hạn thread_id 460000 khỏi mọi báo cáo/feed theo ngày. Kỳ năm 2026 lấy thêm 3.328 đơn. Bản ghi lỗi hoặc thiếu ngày không được âm thầm bỏ: API trả thông tin chất lượng và UI dẫn tới đơn cần đối chiếu.
- Doanh thu chưa VAT = tiền hàng + phí vận chuyển thu khách − chiết khấu − trả hàng đã xác nhận. Tổng tiền khách thanh toán giữ VAT riêng. Các hàm công nợ/hóa đơn/thanh toán giữ nguyên; chỉ sửa phép tính lợi nhuận và cách trình bày.
- Phần lãi xác định dùng giá vốn đã lưu trong dòng đơn; không lấy vốn danh mục hiện tại để tính lại lịch sử. Dòng thiếu vốn có profit=null; tổng chỉ cộng phần xác định và điều chỉnh phí/trả hàng, đi kèm cờ chưa đầy đủ. Giá vốn 0 chỉ được coi là xác nhận khi snapshot có cost_confirmed=true. Giá backfill hiện tại được đánh dấu ước tính, không làm báo cáo thành đủ vốn.
- Phiếu trả chỉ tính khi có hóa đơn KiotViet, chưa xóa; bỏ nháp và khử trùng hóa đơn. Hàng hủy giảm doanh thu, không hoàn vốn. Hàng nhập kho chỉ hoàn vốn theo snapshot/đơn gốc đối chiếu được; mã, giá, lượng và vốn phải đủ căn cứ. Nếu không xác định được, vẫn giảm doanh thu và cảnh báo phần vốn chưa rõ. Bản nhập hóa đơn âm vào orders được khử trùng bằng kiotvietInvoiceID.
- Thêm trường số đơn gốc khi tạo phiếu trả; server kiểm tra đơn còn tồn tại và đúng khách. Không tự gán đơn gốc cho các phiếu lịch sử.
- Lãi vay là **chỉ tiền lãi**, giữ nguyên cấu hình 810 triệu/năm và trọng số tháng. Chỉ toàn doanh nghiệp có lãi sau lãi vay; bộ lọc không bị trừ toàn bộ lãi vay công ty. Bộ lọc thanh toán/mức lãi chỉ xét đơn bán và ghi rõ chưa bù phiếu trả.
- Đếm đơn sản phẩm bằng đơn phân biệt, kể cả kỳ trước và top khách. Resolve danh tính sản phẩm bằng sp_id/mã hiện hành, giữ giá bán/vốn snapshot. Giá bán TB chỉ tính đơn bán; SL và doanh thu có bù hàng trả. Biểu đồ bán ra hỗ trợ cột âm.
- Ẩn biên/tăng trưởng lãi khi thiếu căn cứ; chặn phản hồi kỳ cũ ghi đè kỳ đang chọn. API đọc cùng snapshot cho các phần trong một báo cáo.

## Đối chiếu dữ liệu thật

Snapshot: **2026-09-10T18:41:28.499105+07:00** (giờ Việt Nam). Đơn mới vẫn phát sinh trong lúc sửa nên không
so trực tiếp với snapshot 17:47 của audit ban đầu; cột trước/sau dưới đây dùng
cùng một snapshot.

| Kỳ | Đơn bán trước → sau | Doanh thu trước → sau (đ) | Lãi trước → phần lãi xác định sau (đ) | Đơn thiếu vốn sau sửa |
|---|---:|---:|---:|---:|
| 2026-09-01 → 2026-09-10 | 253 → 253 | 461.910.720 → 459.656.000 | 64.003.164 → 61.748.444 | 3 |
| 2026-08-12 → 2026-09-10 | 801 → 801 | 1.374.351.240 → 1.363.377.000 | 192.109.093 → 181.134.853 | 7 |
| 2026-01-01 → 2026-09-10 | 2906 → 6234 | 5.091.191.694 → 15.217.440.454 | 714.045.994 → 611.909.694 | 3523 |

Tổng doanh thu, vốn, phần lãi xác định, VAT, tổng tiền khách thanh toán và phần
trả hàng đều lệch **0 đồng** so với phép tính độc lập từ JSON. Tổng cột biểu đồ
khớp KPI; tổng báo cáo khách khớp KPI. K2NV120 ngày 07/09 đếm đúng **3 đơn**.

## Những phần dữ liệu vẫn cần đối chiếu

- 7 đơn trong lịch sử chưa có ngày tạo, không thể gán vào kỳ. Cảnh báo xuất hiện gần KPI ở mọi trang lợi nhuận, kèm đường dẫn đơn.
- Kỳ 01/09–10/09 có 3 đơn thiếu vốn, doanh thu tương ứng 4.410.000đ. Kỳ năm có 3.523 đơn thiếu vốn lịch sử, tương ứng 10.565.064.500đ doanh thu. Số lãi năm chỉ là phần đã xác định, không dùng làm kết luận tổng lãi/lỗ.
- Kỳ năm có 3 phiếu trả xác nhận tổng 1.826.000đ; 1 phiếu chưa có kết quả xử lý hàng. Phiếu không có vốn lịch sử rõ ràng không được tự hoàn vốn.
- Dữ liệu phiếu trả hiện không lưu ngày xác nhận riêng. Báo cáo dùng ngày tạo phiếu, sau khi phiếu đã được xác nhận, và kết quả xử lý hàng hiện tại; không phải sổ khóa kỳ bất biến.
- Giá vốn snapshot có sẵn được giữ nguyên; độ chính xác nguồn nhập lịch sử chưa được xác minh lại. Chi phí vận hành và chi phí giao hàng chưa ghi vẫn nằm ngoài phần lãi xác định.

## Kiểm tra và tái lập

- 117 tests Python đạt (lợi nhuận, trả hàng, danh tính sản phẩm, số lượng, thanh toán, khóa hóa đơn và API tạo hóa đơn).
- 11 phản ví dụ audit ban đầu hiện đạt; 57 tests frontend đạt; TypeScript đạt.
- Chrome headless: 320/390/768/1280px, lọc/phân trang/chi tiết, ngày, phản hồi chậm, lỗi và thử lại, dữ liệu thiếu vốn, phiếu trả, ẩn lãi vay cho nhóm và cột trả hàng âm. Không có lỗi JavaScript.
- Snapshot chi tiết: [profit_math_fixed_2026-09-10.json](profit_math_fixed_2026-09-10.json).
- Đối chiếu chỉ đọc: `.venv/bin/python docs/audits/reconcile_profit_math.py`. Baseline ghim vào commit trước sửa. Script dừng để yêu cầu đối chiếu vốn riêng nếu dữ liệu thật phát sinh phiếu nhập lại kho; nhánh này đã có regression tests bằng dữ liệu giả.
- Kiểm tra phản ví dụ: `.venv/bin/python docs/audits/profit_math_checks.py`.

Không sửa dữ liệu đơn/phiếu trả/cấu hình thật trong quá trình kiểm tra.

## Triển khai

Hoàn tất lúc 2026-09-10T18:48:50+07:00.
Server PID 40053, cổng 8090; /app/ và JS/CSS mới trả HTTP 200,
nội dung trùng bản build đã kiểm tra. API lợi nhuận chưa đăng nhập trả 403.
Không có traceback trong log khởi động.

Lần triển khai đầu dừng server rồi gặp lỗi rename khác ổ đĩa (EXDEV). Đã
khởi động lại server ngay khi xử lý tiếp và hoàn tất bằng cách chép asset trước,
thay index.html nguyên tử trên cùng ổ đĩa trong khi server chạy. Backend mới
đã được nạp khi khởi động lại; không cần dừng server thêm.
