# Kiểm kho và điều chỉnh

```mermaid
flowchart TD
    A["Tạo/resume phiếu vị trí<br/>stocktakes.py:194"]
    B["Snapshot remaining<br/>stocktakes.py:214"]
    C["Lock RAM + heartbeat<br/>stocktake_lock.py:22"]
    D["Autosave số đếm<br/>stocktakes.py:250"]
    E["Complete + kiểm stale<br/>stocktakes.py:284"]
    F["Resync giữ actual<br/>stocktakes.py:314"]
    G["Apply stocktake<br/>stocktake_apply.py:23"]
    H["Preflight toàn bộ delta<br/>stocktake_apply.py:42"]
    I["Ghi adjustment<br/>adjustments.py:59"]
    J["allocation = -delta<br/>adjustments.py:87"]
    K["Audit/realtime<br/>stocktake_routes.py:298"]

    A --> B --> C --> D --> E
    E -->|stale| F --> D
    E -->|completed| G --> H --> I --> J --> K
```

- Partial unique index bảo đảm một draft/vị trí (`stocktakes.py:55-59`).
- Lock UI ở RAM process, không bền khi restart/multi-worker (`stocktake_lock.py:6-7`).
- Stale compare lại toàn bộ tập box/remaining mỗi lần đọc draft
  (`stocktakes.py:78-141,144-191`).
- Apply là all-or-nothing và điều chỉnh theo delta snapshot, không ép tồn hiện tại
  về số đã đếm (`stocktake_apply.py:23-69`).
- UI cho admin bấm gỡ cả adjustment từ stocktake, nhưng backend chặn gỡ lẻ
  (`BoxAdjust.tsx:94-118`, `adjustments.py:149-154`).

Phụ thuộc: places, boxes, allocations, adjustment, locks, audit/realtime.
Confidence: **0,93**.

