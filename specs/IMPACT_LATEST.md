# Impact: ngày âm lịch trong calendar

## Target

- `webapp/src/detail/ScrollCalendar.tsx`
- Khối lịch dùng chung sẽ được tách nhỏ trước khi thêm ngày âm lịch.

## Dependents (3)

- `webapp/src/pages/DeliveryCalendar.tsx`: lịch giao hàng.
- `webapp/src/pages/CustomerCalendarPage.tsx`: lịch biến động khách hàng.
- `webapp/src/pages/TasksBoard.tsx`: lịch hạn công việc.

## Affected Stories

Không có `specs/release-plan.yaml` hoặc epic capsule trong repo.

## Test Coverage

- Không có test frontend hiện hữu cho `ScrollCalendar`.
- Cần kiểm tra ngày Tết, ngày thường và tháng âm nhuận.
- Cần build TypeScript và smoke test cả ba màn hình lịch.

## Risk: High

Shared component có ba caller và chưa có test tự động.

## Recommended action

Tách component thành file nhỏ, thêm bộ đổi lịch Việt có nguồn rõ ràng, thêm test ngày mốc, build và kiểm tra DOM trên app thật.

## Prior Art

| Candidate | Source | Verdict | Notes |
| --- | --- | --- | --- |
| `Intl` Chinese calendar | Web Platform Intl | Bỏ | Không bảo đảm lịch Việt UTC+7 ở ngày phân kỳ. |
| `amlich` 0.0.2 | github.com/vanng822/amlich | Bỏ | Cũ, license package không rõ, test rất ít. |
| `@baostudio/viet-lunar` | npm registry | Bỏ | Repo nguồn trả 404 tại lúc kiểm tra. |
| `@sanphandinh/vn-lunar` 1.0.0 | github.com/sanphandinh/vn-lunar | Bỏ | Browser export bị obfuscate và treo Chromium trước DOMContentLoaded. |
| `lunar-date-vn` 1.0.6 | github.com/Hieu-BuiMinh/lunar-date-vn | Dùng | ISC, zero dependency, dựa thuật toán Hồ Ngọc Đức; đã test Node và Chromium. |
