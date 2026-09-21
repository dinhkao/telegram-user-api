# Phiếu mua và nhận hàng NCC

## Luồng hiện tại

```mermaid
flowchart TD
    A["Tạo phiếu mua<br/>PurchaseCreate.tsx:109"]
    B["POST /api/purchases<br/>purchase_routes.py:194"]
    C["Ghi purchase_slips<br/>purchase_store/__init__.py:75"]
    D["Mở modal nhận hàng<br/>PurchaseGoodsModal.tsx:68"]
    E["POST receive-goods<br/>purchase_goods_routes.py:78"]
    F["Derive phần đã nhận<br/>purchase_goods.py:122"]
    G["Validate cả lô<br/>purchase_goods.py:161"]
    H{"Cách nhận<br/>purchase_goods.py:237"}
    I["Tạo thùng mới<br/>purchase_goods.py:257"]
    J["Ghi purchase_in âm<br/>allocations.py:288"]
    K["Tồn kho đổi ngay<br/>queries.py:210"]
    L["POST confirm-goods<br/>purchase_goods_routes.py:117"]
    M["Kiểm đủ + CAS chốt<br/>purchase_goods.py:322"]
    N["Lưu goods_result<br/>purchase_goods.py:351"]
    O["Admin undo<br/>purchase_goods.py:439"]

    A --> B --> C --> D --> E --> F --> G --> H
    H -->|thùng mới| I --> K
    H -->|thùng có sẵn| J --> K
    K --> D
    K --> L --> M --> N --> O --> F
```

## Side effect và guard

- Tạo/cộng thùng chạy trong transaction của `receive_purchase_lines`
  (`server_app/purchase_goods.py:292-319`).
- Gỡ thùng mới đi qua API xoá thùng tổng quát (`inventory_routes.py:721-828`),
  còn gỡ phần cộng đi qua `unreceive_purchase_line` (`purchase_goods.py:359-393`).
- Chốt chỉ thành công khi mọi mã đủ số lượng và CAS chưa bị request khác giành
  (`purchase_goods.py:322-356`).
- Undo kiểm toàn bộ trước, giữ thùng mới và gỡ `purchase_in`
  (`purchase_goods.py:439-507`).
- Realtime và audit chạy tại route sau mutation
  (`purchase_goods_routes.py:44-75,105-114`).

## Phụ thuộc

`purchase_store`, `product_store`, `inventory_store`, auth role, realtime, audit,
product units và cashbox (với phần thanh toán).

Confidence: **0,94**. Chưa xác minh caller bên ngoài webapp của endpoint legacy
`/handle-goods`.

