# Rà soát logic lợi nhuận — 10/09/2026

> **Đã chốt lại quy ước VAT:** Người dùng xác nhận giá vốn đã tính sẵn VAT **bán ra** phải chịu. Vì vậy việc loại VAT thu khách khỏi phép tính lãi trong bản sửa đầu là không phù hợp với quy ước này. Kết luận và số lãi của giai đoạn đó được thay thế bởi [bản điều chỉnh VAT đã xác nhận](profit_math_vat_confirmed_2026-09-10.md).

**Kết luận: có sai lệch đang ảnh hưởng báo cáo.** Phép cộng từ đơn lên tổng quan/biểu đồ khớp nhau, nhưng nguồn đơn, cách xử lý VAT, hàng trả và một số phép đếm chưa đúng với ý nghĩa báo cáo.

Đã đọc code đang triển khai và đối chiếu bản chụp SQLite trong RAM của `app.db` (nguồn mở `mode=ro`, `PRAGMA query_only=ON`). Bản chụp lúc 17:47:33 giờ Việt Nam ngày 10/09/2026 có 18.913 bản ghi orders. Không sửa dữ liệu hoặc công thức đang chạy. Người dùng xác nhận 810.000.000 đồng/năm là **chỉ lãi vay**, không gồm gốc.

Bằng chứng định lượng: [snapshot JSON](profit_math_snapshot_2026-09-10.json). Kiểm thử độc lập: [profit_math_checks.py](profit_math_checks.py); chỉ dùng SQLite trong RAM.

## 1. Nghiêm trọng: báo cáo năm bỏ doanh thu đầu năm nhưng vẫn trừ lãi vay đầu năm

Nguồn: `profit_dashboard/queries.py:14`, `profit_dashboard/compute.py:24–27, 138–140`.

`scan_orders` luôn lọc `thread_id >= 460000`, dù người dùng chọn khoảng ngày nào. Trong dữ liệu hiện có, đơn đầu tiên qua mốc là **04/05/2026**. Chọn 01/01–10/09/2026 vẫn loại **3.328 đơn** từ 01/01–03/05, tổng tiền đơn theo công thức hiện tại **10.223.197.236 đồng**. Trong đó 3.180 đơn có ít nhất một dòng giá vốn.

Đồng thời hệ thống trừ **523.125.000 đồng lãi vay** cho đủ 01/01–10/09. Vì vậy con số “lãi sau vay từ đầu năm” không phải kết quả đầy đủ của khoảng ngày đang ghi trên màn hình. Kỳ trước cũng bị cắt theo cùng mốc, có thể tạo ra so sánh với kỳ không đủ dữ liệu.

Mốc lọc là quy tắc legacy có từ trước. Việc mở rộng preset năm trong lần cải tiến vừa rồi chưa xử lý sự không khớp giữa khoảng chọn và phạm vi dữ liệu. Chưa nên tự bỏ mốc rồi coi dữ liệu cũ là đã chính xác: cần kiểm tra chất lượng các đơn cũ, hoặc giới hạn rõ kỳ khả dụng và không trình bày phần thiếu như doanh thu bằng 0.

## 2. Nghiêm trọng: VAT được cộng trực tiếp vào lợi nhuận

Nguồn: `product_store/profit.py:10–11, 30–36`; `webapp/src/detail/InvoiceEditor.tsx:126–143` có chế độ VAT 8% tiền hàng.

Công thức hiện tại cho đơn có tổng vốn dương:

```text
Lãi = Σ lãi từng dòng có vốn + VAT + PVC − chiết khấu
```

Ví dụ kiểm thử: hàng 100, vốn 60, VAT thu hộ 8 → code trả lãi 48. Lãi kinh doanh trước các chi phí khác phải là 40 khi VAT này là khoản phải nộp/thu hộ; 108 là số tiền khách thanh toán. Nguyên tắc loại khoản VAT thu hộ khỏi doanh thu được mô tả trong [tài liệu IFRS Foundation, Module 23, trang 34–35](https://www.ifrs.org/content/dam/ifrs/supporting-implementation/smes/2025-modules/module-23.pdf#page=34). Đây là tham chiếu về bản chất khoản thu hộ, không phải kết luận doanh nghiệp áp dụng IFRS.

| Kỳ đang kiểm tra | Số đơn có VAT | VAT đang cộng vào lãi |
| --- | ---: | ---: |
| 01–10/09/2026 | 6 | 2.254.720 |
| 12/08–10/09/2026 | 25 | 9.588.240 |
| 01/01–10/09/2026, sau mốc đơn legacy | 113 | 39.151.644 |

Riêng 01–10/09, nếu chỉ loại VAT thu hộ, giữ mọi yếu tố khác như code hiện tại: lãi gộp **63.983.924 → 61.729.204 đồng**, lãi sau vay **47.108.924 → 44.854.204 đồng**. Đây chỉ là điều chỉnh một nguyên nhân, chưa phải kết luận lợi nhuận cuối cùng đúng vì còn thiếu vốn và giới hạn khác bên dưới.

Cần tách tổng thanh toán, doanh thu không gồm VAT và lợi nhuận; không thay công thức tổng tiền khách phải trả. PVC hiện cũng được cộng vào lãi, nhưng chưa có chi phí vận chuyển thực chi đối ứng trong phép tính này.

## 3. Nghiêm trọng: phiếu trả hàng không đi vào báo cáo

Nguồn: `profit_dashboard/compute.py:22–60` chỉ quét orders; `return_store/__init__.py:1–8, 14–31`; `server_app/return_routes.py:214–248` phân biệt phiếu nháp và phiếu đã tạo hóa đơn KiotViet.

Trong năm 2026 có 7 phiếu trả chưa xóa, tổng 2.751.000 đồng. **3 phiếu đã có hóa đơn KiotViet giảm nợ, tổng 1.826.000 đồng**, nhưng báo cáo lợi nhuận không đọc bảng `return_slips`. Không được cộng cả 7 phiếu như giao dịch hoàn tất vì còn phiếu nháp.

Ví dụ thực tế: phiếu #12 ngày 28/08, HĐ `HD086386`, **1.386.000 đồng**, đã xử lý hàng bằng xuất hủy. Phiếu này không giảm doanh thu báo cáo 12/08–10/09. Không có liên kết đơn gốc trong ba phiếu đã lập HĐ, nên chưa thể đối chiếu hoàn vốn theo giá vốn lịch sử một cách chắc chắn. Phiếu nhập kho và phiếu hủy cũng phải được xử lý khác nhau; không thể cứ hoàn doanh thu và cộng lại toàn bộ giá vốn cho mọi phiếu.

Phản ví dụ trong RAM: bán 2 hàng × 100, trả và hủy 1 hàng trị giá 100, phiếu đã lập HĐ → doanh thu code vẫn 200 thay vì 100.

## 4. Lãi sau vay của nhóm lọc đang gánh toàn bộ lãi vay công ty

Nguồn: `profit_dashboard/compute.py:134–140`.

Lợi nhuận được lọc theo khách/SP, còn `loan` chỉ phụ thuộc ngày và cài đặt. Ngày 01–10/09, nhóm đơn chứa `K2NV120` có lãi gộp **5.363.890 đồng** nhưng bị trừ toàn bộ lãi vay kỳ đó **16.875.000 đồng**, ra **−11.511.110 đồng**.

Phép trừ đúng về số học và giao diện đã có cảnh báo, nhưng kết quả này không phải lãi sau phân bổ của riêng SP/nhóm đơn. Cộng kết quả nhiều nhóm sẽ trừ lãi vay nhiều lần. Cần ẩn chỉ số sau vay ở phạm vi nhóm, hoặc xác định một quy tắc phân bổ cộng lại khớp toàn công ty. Lọc mã SP hiện chọn toàn đơn chứa mã, không chỉ riêng các dòng của mã đó.

## 5. Số đơn trong trang chi tiết SP bị đếm theo số dòng hóa đơn

Nguồn: `profit_dashboard/compute.py:265–288, 301, 321–327`.

Mỗi dòng cùng mã SP được append riêng, sau đó `len(orders)` được dùng như số đơn; top khách và kỳ trước cũng tăng số đơn theo dòng. Doanh thu/SL của những dòng này cộng là đúng; lỗi nằm ở số đơn và so sánh số đơn.

Dữ liệu 01–10/09 có 4 đơn chứa lặp mã; 12/08–10/09 có 16 đơn. Ví dụ `K2NV120` ngày **07/09/2026**: trang chi tiết báo **4 đơn**, nhưng chỉ có **3 thread_id khác nhau**; đơn #513847 có hai dòng của cùng mã. Cần đếm `COUNT DISTINCT thread_id` trong kỳ này, kỳ trước và từng khách.

## 6. Đổi mã SP làm tách lịch sử bán và sai báo cáo theo mã hiện tại

Nguồn: `product_store/profit.py:14, 19–31`; `profit_dashboard/compute.py:267, 323`. Trong khi phần hiển thị đơn thông thường đã resolve bằng `sp_id` tại `order_store/display.py`, phần lợi nhuận vẫn trả `code` lấy từ snapshot `sp`, kể cả khi có `sp_id` bất biến.

Có **4 đơn, 1.200.000 đồng tiền hàng** trong kỳ kiểm tra mang mã cũ `DMX` nhưng `sp_id` trỏ tới mã hiện tại `DMXL`. Tra lợi nhuận theo `DMXL` không gom những dòng đó vào. Lỗi làm sai báo cáo theo sản phẩm, không làm mất tổng tiền ở dashboard toàn bộ. Cần resolve danh tính SP để gom nhóm nhưng giữ nguyên giá và vốn đã chốt.

## 7. Các giới hạn làm lợi nhuận chưa đầy đủ, cần hiển thị rõ

- **Thiếu giá vốn:** 01–10/09 có 3 đơn, 4.410.000 đồng doanh thu dòng thiếu vốn. Các dòng đó được gán lãi bằng 0. Vì vậy `461.720.720 − 393.326.796 = 68.393.924` không khớp lãi hiển thị `63.983.924`; chênh đúng 4.410.000. Không thể tự coi toàn bộ chênh này là lãi bị thiếu: giá vốn thật chưa biết. Giao diện hiện đã cảnh báo và không đưa đơn thiếu vốn vào các bộ lọc lỗ/hòa vốn/biên thấp.
- **Giá vốn chưa đóng băng:** trong phạm vi năm sau mốc legacy có 267 dòng lấy vốn hiện tại; sửa danh mục có thể làm đổi lãi lịch sử. Riêng 01–10/09 có 4 dòng như vậy.
- **Ngày tạo đơn khác ngày ghi nhận bán:** 01–10/09 có 10 đơn chưa được đánh dấu giao, tổng 10.179.000 đồng, vẫn được tính. Cờ workflow không đủ để kết luận tất cả chưa bán; cần thống nhất kỳ báo cáo theo tạo đơn hay giao/xuất hóa đơn.
- **Đơn có phiếu thu** vẫn được tính 100% doanh thu/lãi đơn dù mới thu một phần. Đây là lọc tập đơn, không phải báo cáo lợi nhuận theo dòng tiền đã thu. Nhãn hiện đã nói rõ.

## 8. Lỗi biên tái hiện được, chưa thấy trong dữ liệu đang báo cáo

- Dòng `sl=-1, price=100, cost_price=60`: lãi dòng −40 nhưng tổng lãi thành 0 vì kiểm `total_cost > 0`.
- Chỉ có khóa `quantity=2` thay cho `sl`: doanh thu thành 0 dù các đường tổng tiền khác hỗ trợ fallback này.
- `vat=null` làm ném `TypeError`, có thể hỏng toàn bộ kỳ báo cáo thay vì xử lý phí tùy chọn.

Không tìm thấy trường hợp số lượng âm, fallback quantity hoặc lỗi parse làm crash trong tập đơn được báo cáo hiện tại. Chúng là rủi ro tương thích/đầu vào, không phải số sai lệch đã đo trên live.

## 9. Những phép tính đã kiểm tra và đang đúng

Theo xác nhận của người dùng, tiền cấu hình là lãi vay. Tổng trọng số hiện tại = 16 (tháng 1 và 12 mỗi tháng 3, mười tháng còn lại mỗi tháng 1):

```text
Lãi tháng = 810.000.000 × trọng số tháng / 16
Tháng thông thường = 50.625.000
Tháng 1 hoặc 12 = 151.875.000
Lãi 01–10/09 = 50.625.000 × 10/30 = 16.875.000
```

Tổng đủ năm khớp 810.000.000 trong cả 2024 (nhuận), 2025 và 2026. Công thức trọng số tương đương cách code chia 12 rồi chia trọng số trung bình; không có lỗi “chia 12 hai lần”. Đây là kiểm tra đúng theo cài đặt, không đối chiếu với sao kê ngân hàng thực tế.

Tổng tất cả ngày của biểu đồ khớp các KPI doanh thu, vốn, lãi, lãi vay và sau vay; đã kiểm cả ngày không bán. Phần trăm thay đổi dùng trị tuyệt đối kỳ trước nên cải thiện từ lỗ 50 lên lỗ 20 hiện +60%, đúng với quy ước đã ghi. Preset đếm cả hai đầu và tính giờ Việt Nam đã có kiểm thử.

## 10. Kiểm thử và thứ tự xử lý

- Bộ test lợi nhuận hiện hữu: **34 đạt, 10 subtest đạt**.
- Bộ kiểm tra toán độc lập trong tài liệu này: **11 ca — 3 đạt, 7 assertion lệch, 1 lỗi runtime**. Chạy riêng, không thêm test đỏ vào suite mặc định của ứng dụng.
- `tests/test_profit.py:27–33` hiện kiểm rằng VAT được cộng vào lãi, tức đang khóa hành vi cũ. Việc suite cũ đạt không chứng minh quy tắc đó đúng nghiệp vụ.

Ưu tiên: (1) sửa phạm vi năm/kỳ trước và tách VAT khỏi lãi; (2) đưa phiếu trả đã xác nhận vào báo cáo, phân biệt nhập kho/hủy; (3) thống nhất lãi vay của phạm vi lọc; (4) sửa đếm đơn và gom mã theo danh tính; (5) xử lý chất lượng giá vốn và đầu vào. Báo cáo này chỉ kiểm tra, chưa thay công thức server hay dữ liệu thật.


Cập nhật sau khi sửa: xem [kết quả sửa và đối chiếu](profit_math_fix_2026-09-10.md). Các phát hiện ở trên mô tả trạng thái trước sửa.
