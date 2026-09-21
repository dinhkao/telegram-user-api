# Báo cáo trùng lặp và nguồn gây phức tạp

## 1. Phép tính tồn bị viết lại khắp hệ thống

Định nghĩa đúng hiện tại là `remaining = inventory_boxes.quantity -
SUM(box_allocations.quantity)`, nhưng nó được viết lại tại:

- `inventory_store/queries.py:210-243,259-287`
- `inventory_store/allocations.py:89-102,241-246,293-307`
- `server_app/purchase_goods.py:94-115,219-224,384-389,490-495`
- `inventory_store/adjustments.py:49-56`
- `inventory_store/stocktakes.py:78-99,214-232`
- `server_app/inventory_audit.py:15-27`
- `server_app/product_timeline.py:76-118`
- `server_app/place_timeline.py:71-124`
- `server_app/box_timeline.py:76-86`

Đây là duplication **ngẫu nhiên**, không phải chuyên biệt hợp lệ. Các nơi còn dùng
epsilon khác nhau (`1e-9`, `1e-6`, `0.000000001`, `0.0001`), nên summary, guard,
kiểm kho và timeline có thể bất đồng về “còn hàng”.

**Hợp nhất:** một balance query/CTE chuẩn và một `STOCK_EPS` trong
`inventory_store`; không lưu thêm cột remaining.

## 2. Movement ledger thống nhất, nhưng reference sai nghĩa

`box_allocations` được tái sử dụng tốt cho tám loại movement, nhưng cột
`order_thread_id` đang mang nhiều loại ID:

| kind | dấu | `order_thread_id` thực chất là | nguồn |
|---|---:|---|---|
| order | + | đơn hàng | `allocations.py:62-112` |
| production | + | phiếu SX | `allocations.py:115-153` |
| disposal | + | phiếu huỷ | `disposal_store/__init__.py:61-90` |
| transfer_out/in | +/- | thùng đối tác | `allocations.py:203-257` |
| return_in | - | phiếu trả | `allocations.py:260-285` |
| purchase_in | - | phiếu mua | `allocations.py:288-290` |
| adjustment | `-delta` | phiếu điều chỉnh | `adjustments.py:80-92` |

Giữ một ledger là **đúng**; tên/reference bị quá tải là **ngẫu nhiên**. Hậu quả
thấy ngay ở thu hồi đơn: route kiểm ref ID nhưng không kiểm `kind='order'`
(`inventory_routes.py:1434-1439`).

**Hợp nhất:** dùng khái niệm `ref_type/ref_id`; ít nhất đổi tên trong domain/API
trước, migration cột sau. Không tách thành tám bảng ledger.

## 3. Hai engine nhập + chốt phiếu mua

> Trạng thái đồng thời: lúc bắt đầu audit, HEAD sạch còn đầy đủ đường legacy dưới
> đây. Trong lúc audit xuất hiện diff chưa commit xóa backend legacy ở
> `app_factory.py`, `purchase_goods.py`, `purchase_goods_routes.py`, nhưng chưa sửa
> hết client/tests. Ở lần kiểm tra cuối, test đã bỏ import nhưng còn 15 chỗ gọi
> `apply_purchase_receipt` nên suite purchase lỗi `NameError`. Báo cáo giữ phân tích
> HEAD ban đầu và coi diff này là WIP bên ngoài phạm vi audit.

- Luồng chính: `receive_purchase_lines()` + `confirm_purchase_receipt()`
  (`purchase_goods.py:292-356`).
- Luồng legacy one-shot: `apply_purchase_receipt()`
  (`purchase_goods.py:396-436`).
- Hai surface HTTP: `purchase_goods_routes.py:78-151,193-232`.
- Client legacy không có caller UI: `webapp/src/api.ts:444-447`; UI dùng API mới
  tại `api.ts:449-457`.

Legacy path lặp đọc phiếu, derive draft, validate, apply, CAS, kiểm thiếu, snapshot
và audit. Đây là duplication **ngẫu nhiên do tương thích cũ**.

**Hợp nhất:** xoá endpoint/export/engine legacy sau khi xác minh không có client
ngoài. Giữ receive nhiều đợt + confirm riêng.

## 4. Một receipt có ba biểu diễn trạng thái

- Live draft derive từ boxes + purchase movements: `_draft_receipt()`
  (`purchase_goods.py:122-158`).
- Trạng thái đóng: `goods_handled_at/by` (`purchase_goods.py:345-350`).
- Snapshot trùng dữ liệu: `goods_result` (`purchase_goods.py:285-289,351-353`).

View còn phải rẽ nhánh giữa live và snapshot (`purchase_goods_view.py:32-57`).
Marker đóng là cần thiết; snapshot thùng trong `goods_result` phần lớn **trùng** với
nguồn live và audit.

**Hợp nhất:** giữ `goods_handled_at/by`, luôn đọc receipt entries từ source thùng
và movement; lịch sử đã có audit. Bỏ `goods_result` sau migration kiểm chứng.

## 5. Cùng định nghĩa “hàng đã nhận” bị query ba lần

- Detail: `_draft_receipt()` (`purchase_goods.py:122-158`).
- Guard sửa phiếu: `_retained_box_totals()` (`purchase_store/__init__.py:139-167`).
- Badge dashboard: `batch_draft_status()` (`purchase_store/__init__.py:284-314`).

Output detail/tổng/boolean là chuyên biệt hợp lệ; việc mỗi nơi tự định nghĩa hai
nguồn `source_purchase_id` và `purchase_in` là duplication ngẫu nhiên.

**Hợp nhất:** một read model receipt entries; projection batch vẫn dùng SQL batch.

## 6. Chuẩn hoá product identity và đơn vị bị lặp

- Python limits: `purchase_goods.py:43-79`.
- Python totals guard: `purchase_store/__init__.py:170-199`.
- UI progress: `PurchaseDetail.tsx:273-291`.
- UI prefill/cap: `PurchaseGoodsModal.tsx:37-65,94-99`.

Server/client cùng validate là hợp lệ; hai bản trong cùng layer là ngẫu nhiên.

**Hợp nhất:** một helper Python và một helper TypeScript; server vẫn là nguồn
quyết định.

## 7. Purchase receipt và return receipt trùng primitive

- Purchase tạo/cộng thùng: `purchase_goods.py:195-268`.
- Return tạo/cộng thùng: `return_goods.py:55-96`.
- Lõi receive chỉ khác kind/ref: `allocations.py:260-290`.

Lifecycle purchase nhiều đợt và nhánh dispose của return là chuyên biệt hợp lệ.
Validation thùng, tạo thùng, snapshot và touched-box collection là trùng ngẫu nhiên.
Return hiện còn yếu hơn: không check cùng SP, disabled hay trần phiếu
(`return_goods.py:69-83`).

**Hợp nhất:** hai primitive strict `receive_existing` và `receive_new`; policy
purchase/return vẫn nằm ở service riêng.

## 8. Audit snapshot bị nhân bản

- Canonical hiện tại: `inventory_audit.box_snapshot()`
  (`inventory_audit.py:15-27`).
- Bản gần giống trong purchase: `_audit_snap()`
  (`purchase_goods.py:102-119`).

Purchase tránh import tầng aiohttp là lý do hợp lệ; canonical nằm sai tầng khiến
duplication trở thành ngẫu nhiên.

**Hợp nhất:** chuyển snapshot thuần xuống `inventory_store`; caller chỉ enrich
`taken`, `order_id`, `source_id`.

## 9. Timeline lặp event catalog và delta

- `box_timeline.py:19-73`
- `place_timeline.py:20-68`
- `product_timeline.py:21-73`

Scope/filter khác nhau là chuyên biệt; action → label/direction/delta, epoch và
box number là trùng ngẫu nhiên.

**Hợp nhất:** một `inventory_event_spec.py`; mỗi timeline giữ query và aggregate
đặc thù.

## 10. Transaction không nhất quán giữa feature

Purchase, return, disposal, adjustment và stocktake đều có transaction ngoài cho
command (`purchase_goods.py:292-319`, `return_goods.py:39-119`,
`disposal_store/__init__.py:74-90`, `stocktake_apply.py:23-69`). Riêng nhập từ SX
gọi tạo thùng → cập nhật phiếu → trừ BOM qua các transaction/commit tách rời
(`inventory_routes.py:291-309`, `queries.py:65-91`,
`production_store/queries.py:187-199`).

Đây là divergence ngẫu nhiên và có thể để lại thành phẩm đã tạo nhưng nguyên liệu
chưa trừ nếu lỗi giữa chuỗi.

**Hợp nhất:** một service command production receipt, một transaction ngoài.

## 11. Permission và policy bị hard-code nhiều nơi

Tài liệu mô tả adjustment/apply stocktake admin-only (`CLAUDE.md:271-285`), nhưng
HEAD hiện tại dùng office ở backend (`adjustment_routes.py:41-46`,
`stocktake_routes.py:257-266`) và frontend (`BoxAdjust.tsx:14,61-67`,
`StocktakeDetail.tsx:188-192`). Test quyền được nhắc trong tài liệu cũng không tồn
tại ở worktree hiện tại.

Front/back gating là cần thiết; lặp policy không có regression test là nguyên nhân
drift. Server phải là nguồn quyền, client chỉ phản chiếu capability.

## Không nên hợp nhất

- Wrapper `receive_return_stock`/`receive_purchase_stock` trên primitive chung
  (`allocations.py:260-290`) đang rõ nghĩa và nên giữ.
- Guard undo khác nhau giữa order, production, purchase, disposal và adjustment là
  chuyên biệt nghiệp vụ; chỉ nên dùng chung primitive ledger, không dựng state
  machine tổng quát.
- Các transition save/complete/resync/void của stocktake có ý nghĩa khác nhau;
  không nên gom thành registry/factory.

Confidence: **0,93**. Đây là static trace; chưa profile latency/query count trên dữ
liệu production.
