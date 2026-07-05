"""Core order domain store (orders, customers, tasks, parsers, serialization, Firebase mirror) -> shared SQLite (SHARED_DB_PATH), product_store, Firebase, KiotViet. Root shim: order_db.py."""
from .schema import SHARED_DB_PATH, MIRROR_FIELDS, _get_connection, transaction
from .serialization import get_order_by_thread_id, _get_order_firebase_key, _save_order, _update_order_json_field, _create_order, get_order_json
from .orders import delete_order, get_order_html, set_order_flag, save_order_invoice
from .tasks import _all_steps_done, set_task_status, clear_task_status, get_all_tasks, sort_tasks
from .custom_tasks import add_custom_task, remove_custom_task
from .customers import search_customers, add_customer, update_customer, get_customer_kv_id, get_customer_by_key, touch_customer_last_order, update_customer_debt
from .search import search_products, get_customer_price_list, _invalidate_customer_patterns_cache
from .comma_parser import _parse_no_qc, _parse_qc, parse_comma_text
from .free_text import parse_invoice_free_text
from .task_admin import delete_all_tasks, migrate_tasks_to_v2
from .customer_detect import detect_customer_free_text

__all__ = [
    "SHARED_DB_PATH",
    "MIRROR_FIELDS",
    "_get_connection",
    "transaction",
    "get_order_by_thread_id",
    "_get_order_firebase_key",
    "_save_order",
    "_update_order_json_field",
    "_create_order",
    "get_order_json",
    "delete_order",
    "get_order_html",
    "set_order_flag",
    "save_order_invoice",
    "_all_steps_done",
    "set_task_status",
    "clear_task_status",
    "add_custom_task",
    "remove_custom_task",
    "get_all_tasks",
    "delete_all_tasks",
    "sort_tasks",
    "migrate_tasks_to_v2",
    "search_customers",
    "add_customer",
    "update_customer",
    "get_customer_kv_id",
    "get_customer_by_key",
    "touch_customer_last_order",
    "update_customer_debt",
    "search_products",
    "get_customer_price_list",
    "detect_customer_free_text",
    "_invalidate_customer_patterns_cache",
    "_parse_no_qc",
    "_parse_qc",
    "parse_comma_text",
    "parse_invoice_free_text",
]
