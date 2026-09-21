# Kho lõi và phép tính tồn

```mermaid
flowchart TD
    A["Tạo thùng vật lý<br/>queries.py:49"]
    B["inventory_boxes.quantity gốc<br/>schema.py:12"]
    C["Ghi biến động<br/>allocations.py:62"]
    D["box_allocations.quantity có dấu<br/>allocations.py:21"]
    E["CTE SUM allocation<br/>queries.py:210"]
    F["remaining = quantity - SUM<br/>queries.py:237"]
    G["Dashboard theo SP<br/>queries.py:259"]
    H["Chi tiết thùng/SP/vị trí<br/>inventory_routes.py:955"]

    A --> B --> E
    C --> D --> E --> F
    F --> G
    F --> H
```

- `inventory_boxes` giữ danh tính thùng, nguồn, vị trí và số lượng gốc
  (`schema.py:12-29,60-115`).
- Tồn không phải cột lưu sẵn; allocation dương giảm tồn, âm tăng tồn
  (`queries.py:210-243`).
- `box_code` tái sử dụng; `id` mới là danh tính bất biến (`schema.py:32-35`).
- Cùng công thức remaining được viết lại ở allocations, stocktake, purchase,
  timeline và demand thay vì một read model chuẩn.

Phụ thuộc: `products`, `orders`, places, units, audit events. Confidence: **0,96**.

