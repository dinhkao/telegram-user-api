# Xuất kho cho đơn

```mermaid
flowchart TD
    A["POST allocate<br/>inventory_routes.py:1345"]
    B["Kiểm khóa đơn<br/>order_stock_lock.py:29"]
    C["allocate_picks<br/>allocations.py:62"]
    D["Skip/clip từng pick<br/>allocations.py:74"]
    E["Ghi kind=order dương<br/>allocations.py:103"]
    F["Chốt xuất kho<br/>order_stock_lock.py:47"]
    G["So invoice với allocations<br/>order_stock_lock.py:89"]
    H["Ghi stock_confirmed<br/>order_stock_lock.py:111"]
    I["Thu hồi allocation<br/>inventory_routes.py:1403"]

    A --> B --> C --> D --> E --> F --> G --> H
    I --> B --> E
```

- Chốt server kiểm cả thiếu lẫn dư (`order_stock_lock.py:89-129`).
- `allocate_picks` bỏ lặng pick sai và clip số vượt tồn; route vẫn có thể trả thành
  công với danh sách rỗng (`allocations.py:74-112`, `inventory_routes.py:1387-1400`).
- Thu hồi kiểm `order_thread_id` nhưng không kiểm `kind='order'`
  (`inventory_routes.py:1434-1439`), là hệ quả nguy hiểm của khóa tham chiếu bị quá tải.

Phụ thuộc: order JSON, inventory, locks, realtime/audit. Confidence: **0,95**.

