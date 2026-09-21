# Nhập kho từ sản xuất và BOM

```mermaid
flowchart TD
    A["POST production boxes<br/>inventory_routes.py:141"]
    B["Kiểm phiếu/capability/settings<br/>inventory_routes.py:181"]
    C["Tính BOM chính/phụ<br/>inventory_routes.py:218"]
    D["Kiểm thùng NL, kho phụ, cap<br/>inventory_routes.py:232"]
    E["Tạo thùng thành phẩm<br/>inventory_routes.py:292"]
    F["Cập nhật số phiếu SX<br/>inventory_routes.py:295"]
    G["Trừ NL kind=production<br/>inventory_routes.py:299"]
    H["Realtime + audit<br/>inventory_routes.py:327"]

    A --> B --> C --> D --> E --> F --> G --> H
```

Nhánh này chứa nhiều rule nghiệp vụ chính đáng: loại phiếu, BOM chính/phụ,
`aux_required`, kho NL phụ và capability sản phẩm (`inventory_routes.py:192-290`).
Tuy nhiên tạo thùng, cập nhật phiếu và trừ NL hiện gọi ba hàm tự quản transaction,
không có một transaction ngoài bao cả chuỗi (`inventory_routes.py:292-300`).

Phụ thuộc: production, product, recipe, settings, inventory, audit/realtime.
Confidence: **0,94**.

