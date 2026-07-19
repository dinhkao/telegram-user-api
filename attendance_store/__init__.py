"""attendance_store — sự kiện CHẤM CÔNG từ máy Ronald Jack (app.db).

Collector Windows đọc máy chấm công qua SDK ZKTeco, gửi batch HTTPS (Tailscale) vào
POST /api/attendance/events (server_app/attendance_routes.py). Lưu RAW punch bất biến
(event_id SHA-256 UNIQUE = idempotent); map employee_code → production_workers.id qua
attendance_employee_map. SỬA TAY = lớp hiệu chỉnh phủ lên raw (edits.py: thêm giờ tay
+ ẩn giờ máy — không sửa raw nên máy gửi lại không đè). Lương/ca tính SAU từ raw
(chưa làm — xem salary_store 'time').
"""
from attendance_store.edits import (
    add_manual,
    delete_manual,
    set_suppressed,
    day_detail,
)
from attendance_store.store import (
    ensure_schema,
    insert_events,
    list_events,
    day_summary,
    unmapped_codes,
    list_mappings,
    map_employee_code,
    last_sync,
)
from attendance_store.domain import validate_batch, token_ok

__all__ = [
    "ensure_schema", "insert_events", "list_events", "day_summary",
    "unmapped_codes", "list_mappings", "map_employee_code", "last_sync",
    "add_manual", "delete_manual", "set_suppressed", "day_detail",
    "validate_batch", "token_ok",
]
