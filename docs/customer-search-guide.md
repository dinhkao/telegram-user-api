# Hướng dẫn tìm kiếm dữ liệu khách hàng

## Database

File: `~/letrang-db/app.db` (SQLite, biến môi trường `SHARED_DB_PATH`)

## Table `customers`

```sql
CREATE TABLE customers (
    firebase_key TEXT PRIMARY KEY,
    json         TEXT NOT NULL,       -- JSON chứa toàn bộ thông tin khách hàng
    updated_at   INTEGER NOT NULL,
    deleted_at   INTEGER              -- NULL = còn sống, có giá trị = đã xoá
);
```

### Cách search

```sql
-- Tìm theo tên (JSON LIKE)
SELECT firebase_key, json FROM customers
WHERE deleted_at IS NULL
  AND json LIKE '%Minh%'
  AND json LIKE '%chợ%'
LIMIT 10;

-- Hoặc tìm theo firebase_key
SELECT json FROM customers
WHERE firebase_key = '26'
  AND deleted_at IS NULL;

-- Tìm tất cả khách hàng (chưa xoá)
SELECT firebase_key, json FROM customers WHERE deleted_at IS NULL;
```

### Field trong JSON

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `name` | string | Tên khách hàng |
| `kh_id` | int | ID trên KiotViet |
| `debt` | int | Nợ (VNĐ) |
| `price_list` | int | ID bảng giá (tham chiếu `bang_gia_moi` trong `kv_store`) |
| `personal_price_list` | dict | Giá riêng cho từng sản phẩm (VD: `{"K10LV85": 14000}`) |
| `patterns` | array[string] | Từ khoá detect khách hàng từ text |
| `thread_id` | int | Thread ID trên Telegram |
| `message_id_in_customer_channel` | int | Message ID trong channel khách hàng |
| `last_order_at` | string (ISO) | Thời gian đơn cuối |
| `latest_hd` | dict | Thông tin đơn hàng gần nhất |
| `note` | string | Ghi chú |

## Bảng giá (`kv_store`)

Key: `bang_gia_moi`, value là JSON object chứa tất cả bảng giá:

```json
{
  "5": {
    "name": "Chợ Long Hoa",
    "price_list": {"K10LV85": 16500, ...}
  },
  "155": {
    "name": "Tuyết Điểm thường",
    "price_list": {"K10LV87": 14200, ...}
  },
  "160": {
    "name": "npp 2026",
    "price_list": {"K10LV85": 15000, ...}
  }
}
```

### Cách lấy bảng giá của 1 khách hàng

Trong code: `get_customer_price_list(conn, firebase_key)` ở `order_store/search.py`

Logic:
1. Lấy `price_list` từ JSON của khách hàng → tìm trong `bang_gia_moi`
2. Merge với `personal_price_list` (nếu có) → ghi đè lên bảng giá chung

### Cách update

```python
import json, sqlite3
from datetime import datetime, timezone

conn = sqlite3.connect('/path/to/app.db')
now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')

# Đọc cũ
row = conn.execute("SELECT json FROM customers WHERE firebase_key = ?", ('26',)).fetchone()
data = json.loads(row[0])

# Sửa
data['price_list'] = 160
data.pop('personal_price_list', None)

# Ghi lại
conn.execute(
    "UPDATE customers SET json = ?, updated_at = ? WHERE firebase_key = ?",
    (json.dumps(data, ensure_ascii=False), now, '26')
)
conn.commit()
```

## Code liên quan

| File | Chức năng |
|---|---|
| `order_store/customers.py` | CRUD khách hàng: `search_customers`, `add_customer`, `update_customer`, ... |
| `order_store/search.py` | `get_customer_price_list`, `search_products` |
| `order_store/schema.py` | Kết nối database (`_get_connection`) |
| `command_handlers/order_commands_v2_customer_search.py` | Format kết quả search |
| `command_handlers/order_commands_v2_customer.py` | Handler Telegram: `customer search`, `add khach hang`, `editkh` |

## Lưu ý

- `deleted_at IS NULL` = khách hàng còn hoạt động
- `firebase_key` thường là tên viết thường + underscore (VD: `26` hoặc `a_minh_chợ_đêm`)
- Bảng giá NPP = key `160` (npp 2026)
