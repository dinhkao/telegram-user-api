# Handoff prompts cho `/make-plan`

## 1. Chốt lỗi an toàn trước refactor

```text
/make-plan Sửa và khóa regression cho bốn lỗi kho hiện tại:
1) adjustment create và stocktake apply phải admin-only tại
server_app/adjustment_routes.py:41-46, server_app/stocktake_routes.py:257-266,
BoxAdjust.tsx:14-67 và StocktakeDetail.tsx:188-192;
2) return restock_existing validate box tồn tại, enabled, đúng product và không
vượt dòng trả tại server_app/return_goods.py:55-96;
3) order release check kind='order' tại inventory_routes.py:1434-1439;
4) route không báo ok nếu allocate/release không áp dụng dòng hợp lệ.
Đọc 01-flowcharts/order-stock.md, transfer-return-disposal.md và
stocktake-adjustment.md. Thêm regression tests. Không đổi policy khác, không mở
rộng UI.
```

## 2. Canonical balance

```text
/make-plan Tạo inventory_store/balances.py với STOCK_EPS, CTE balance chuẩn,
get_box_state và batch query. Rewrite inventory_store/queries.py:210-310,
allocations.py:89-102,241-246,293-307, purchase_goods.py:94-115,219-224,384-495,
adjustments.py:49-56, stocktakes.py:78-99,214-232, inventory_audit.py:15-27 và
current-balance queries trong ba timeline. Đọc 01-flowcharts/core-inventory.md và
02-duplication-report.md mục 1. Không thêm cột remaining/cache, không đổi dấu dữ
liệu hiện tại, không tạo repository/factory tổng quát. Giữ batch SQL hiệu quả và
thêm tests boundary epsilon.
```

## 3. Đơn giản hóa purchase receipt

```text
/make-plan Hợp nhất nhập kho phiếu mua thành một command
mutate_purchase_receipt(conn, purchase_id, lines, close) và endpoint
POST /api/purchases/{id}/receipt. Rewrite purchase_goods.py:292-356,396-436,
purchase_goods_routes.py:78-232, api.ts:444-457, PurchaseGoodsModal.tsx:116-164 và
PurchaseDetail.tsx:345-365. Xác minh không có external caller rồi xóa /handle-goods
và handlePurchaseGoods. Giữ nhập nhiều đợt, confirm atomic, unreceive và admin
undo. Migration bỏ goods_result: giữ goods_handled_at/by, luôn derive entries từ
source_purchase_id + purchase_in; audit giữ lịch sử. Đọc
01-flowcharts/purchase-receipt.md và 02-duplication-report.md mục 3-6. Không giữ hai
đường sau feature flag, không tạo state machine/registry.
```

## 4. Movement và receipt primitives strict

```text
/make-plan Chuẩn hóa ledger kho thành domain movement với ref_type/ref_id và strict
validation mặc định. Target inventory_store/movements.py::issue_stock,
receive_stock, transfer_stock, reverse_movements và inventory_store/receipts.py::
receive_into_existing, receive_as_new_boxes. Rewrite allocations.py:62-290,
purchase_goods.py:195-268, return_goods.py:55-96, disposal_store/__init__.py:61-90
và adjustments.py:87-92. Đọc 01-flowcharts/core-inventory.md,
transfer-return-disposal.md và 02-duplication-report.md mục 2,7. Policy purchase
cap/BOM/order invoice/return dispose phải ở service riêng. Không tách nhiều bảng
ledger, không làm generic disposition framework, không silent skip/clip mặc định.
```

## 5. Transaction hóa nhập sản xuất

```text
/make-plan Tách nhập thùng SX thành
server_app/production_inventory.py::create_production_inventory với một transaction
bao validate-final, add_boxes, production add_number/total và movement tiêu hao.
Rewrite inventory_routes.py:141-337, queries.py:49-91,
production_store/queries.py:187-199 và allocations.py:62-112 để store con không
bare-commit cắt transaction. Đọc 01-flowcharts/production-bom.md và
02-duplication-report.md mục 10. Giữ nguyên rule san_xuat/dong_goi, BOM chính/phụ,
aux_source, capability và audit. Không gom Telegram topic creation vào DB
transaction; thêm fault-injection tests ở từng bước.
```

## 6. Snapshot, timeline và dashboard

```text
/make-plan Hợp nhất read-side kho: (1) chuyển box_snapshot thuần sang
inventory_store/snapshots.py và rewrite inventory_audit.py:15-27,
purchase_goods.py:102-119 cùng các enrich call sites; (2) tạo
server_app/inventory_event_spec.py cho action→delta/direction/reason và rewrite
box_timeline.py:19-73, place_timeline.py:20-68, product_timeline.py:21-73;
(3) thiết kế GET /api/inventory/dashboard thay ba request tại khoData.ts:22-31 bằng
một snapshot nhất quán. Đọc 01-flowcharts/analytics-read-models.md và
02-duplication-report.md mục 8-9. Không tạo event bus/registry tổng quát, không đổi
audit schema cùng phase, giữ fallback audit/media và giới hạn timeline.
```

## 7. Đơn giản hóa UX nhập hàng

```text
/make-plan Refine UX dựa trên receipt API đã hợp nhất. Trong
PurchaseGoodsModal.tsx:18-247, mặc định Tạo thùng mới và prefill đơn vị; đưa Nhập
thùng có sẵn/Bỏ qua vào Tùy chọn. Nút chính Nhập đủ & chốt, nút phụ Lưu đợt này.
Trong PurchaseDetail.tsx:268-417 chỉ hiện progress, Nhập tiếp và trạng thái
chốt/undo. Đọc 01-flowcharts/purchase-receipt.md và 03-unified-proposal.md mục 7.
Không xóa nhập nhiều đợt, không auto-skip, không giấu lỗi thiếu/vượt, không nhân
bản logic product identity/unit conversion.
```
