from __future__ import annotations

from aiohttp import web

from server_app.audit import audit_middleware
from server_app.config import PORT
from server_app.cors import cors_middleware
from server_app.comment_routes import comments_add_handler, comments_list_handler
from server_app.customer_routes import (
    customer_detail_handler, customer_refresh_debt_handler, customers_search_handler,
    customer_update_handler, customer_orders_handler,
    customer_kv_search_handler, customer_kv_link_handler, customer_kv_unlink_handler,
    customer_delete_handler,
)
from server_app.customer_feed import customer_feed_handler
from server_app.price_list_routes import price_lists_handler, price_list_detail_handler, price_list_save_handler, price_one_save_handler, price_list_history_handler
from server_app.donhang_routes import donhang_handler, donhang_msg_handler, donhang_page_handler, donhang_stats_handler
from server_app.image_routes import (
    image_comments_add_handler, image_comments_delete_handler, image_comments_list_handler,
    images_delete_handler, images_file_handler, images_kind_handler, images_list_handler, images_upload_handler,
)
from server_app.entity_media_routes import (
    comments_add_handler as em_comments_add, comments_list_handler as em_comments_list,
    images_delete_handler as em_images_delete, images_file_handler as em_images_file,
    images_list_handler as em_images_list, images_upload_handler as em_images_upload,
)
from server_app.order_api_auto import auto_parse_handler, order_preview_handler, customer_price_list_handler
from server_app.order_api_create import order_create_handler
from server_app.order_api_delete import order_delete_handler
from server_app.order_api_mutations import api_assign_customer_handler, api_fix_handler, api_invoice_update_handler, api_refresh_handler, api_reply_handler, api_set_ngay_giao_handler
from server_app.order_api_payments import api_customer_price_handler, order_totals_handler, payment_ck_handler, payment_delete_handler, payment_tm_handler
from server_app.order_api_print import api_print_giao_handler
from server_app.order_api_tasks import _make_task_handler, api_task_handler, api_task_status_clear_handler
from server_app.order_api_custom_tasks import add_custom_task_handler, remove_custom_task_handler
from server_app.order_api_invoice import api_create_invoice_handler, api_delete_invoice_handler, api_ensure_invoice_image_handler, api_invoice_html_handler, api_refresh_debt_handler
from server_app.order_history import order_history_handler
from server_app.orders_api import order_detail_handler, orders_api_handler, orders_delivery_handler
from server_app.product_routes import (
    products_search_handler, product_create_handler, product_kiotviet_search_handler,
    product_link_handler, product_unlink_handler, product_delete_handler, product_update_handler, product_rename_handler,
    product_kv_create_handler, kiotviet_categories_handler,
)
from server_app.production_routes import (
    production_add_number_handler,
    production_catalog_handler,
    production_create_handler,
    production_delete_handler,
    production_detail_handler,
    production_list_handler,
    production_set_note_handler,
    production_set_kind_handler,
    production_report_parse_handler,
    production_report_save_handler,
    production_report_lock_handler,
    production_report_lock_status_handler,
    production_report_unlock_handler,
    production_report_draft_handler,
    production_set_product_handler,
    production_set_target_handler,
    production_slip_lock_handler,
    production_slip_unlock_handler,
)
from server_app.banner_routes import banner_pins_handler, banner_pin_create_handler, banner_pin_delete_handler
from server_app.inventory_routes import (
    production_add_boxes_handler,
    production_boxes_list_handler,
    inventory_list_handler,
    all_boxes_handler,
    unplaced_count_handler,
    places_list_handler,
    place_create_handler,
    place_rename_handler,
    place_delete_handler,
    units_list_handler,
    unit_create_handler,
    unit_delete_handler,
    inventory_detail_handler,
    product_orders_handler,
    box_detail_handler,
    box_update_handler,
    box_delete_handler,
    box_transfer_handler,
    recipe_get_handler,
    recipe_set_handler,
    recipe_delete_handler,
    box_disable_handler,
    order_allocations_handler,
    order_allocate_handler,
    order_release_handler,
)
from server_app.orders_pages import order_detail_page_handler, orders_page_handler
from server_app.web_auth import login_handler, me_handler, web_auth_middleware
from server_app.web_pages import index_handler
from server_app.quy_routes import (
    quy_list_handler,
    quy_detail_handler,
    quy_create_handler,
    quy_delete_handler,
)
from server_app.user_routes import (
    users_list_handler,
    users_create_handler,
    users_role_handler,
    users_disabled_handler,
    users_pin_handler,
)
from server_app.webapp_routes import register_webapp_routes
from server_app.websocket_routes import websocket_handler
from server_app import state


def create_app():
    from tg_edit import make_handler as make_edit_handler
    from tg_send import make_handler as make_send_handler
    from tg_send_file import make_handler as make_send_file_handler

    # client_max_size 32MB: mặc định aiohttp 1MB quá nhỏ cho upload ảnh gốc / gửi
    # file lớn (vd APK qua /api/tg/send-file). Tailscale/LAN nội bộ nên nới an toàn.
    app = web.Application(client_max_size=32 * 1024 * 1024,
                          middlewares=[cors_middleware, audit_middleware, web_auth_middleware])
    r = app.router
    r.add_post("/api/auth/login", login_handler)
    r.add_get("/api/auth/me", me_handler)
    r.add_get("/", index_handler)
    r.add_get("/ws", websocket_handler)
    r.add_get("/api/donhang", donhang_handler)
    r.add_get("/api/donhang/stats", donhang_stats_handler)
    r.add_get("/api/donhang/msg", donhang_msg_handler)
    r.add_get("/donhang", donhang_page_handler)
    r.add_get("/orders", orders_page_handler)
    r.add_get("/orders/{thread_id}", order_detail_page_handler)
    r.add_get("/api/orders", orders_api_handler)
    r.add_get("/api/orders/delivery", orders_delivery_handler)
    r.add_get("/api/order/{thread_id}", order_detail_handler)
    r.add_delete("/api/order/{thread_id}", order_delete_handler)
    r.add_static("/static/", "static")
    register_webapp_routes(r)
    get_client = lambda: state._tg_gateway or state._client
    r.add_post("/api/tg/edit-message", make_edit_handler(get_client))
    r.add_post("/api/tg/send-message", make_send_handler(get_client))
    r.add_post("/api/tg/send-file", make_send_file_handler(get_client))
    r.add_post("/api/order/payment/tm", payment_tm_handler)
    r.add_post("/api/order/payment/ck", payment_ck_handler)
    r.add_post("/api/order/payment/delete", payment_delete_handler)
    r.add_post("/api/order/totals", order_totals_handler)
    r.add_post("/api/order/auto-parse", auto_parse_handler)
    r.add_post("/api/order/preview", order_preview_handler)
    r.add_get("/api/customer/{key}/price-list", customer_price_list_handler)
    r.add_post("/api/order/soan", _make_task_handler("soan"))
    r.add_post("/api/order/ban", _make_task_handler("ban"))
    r.add_post("/api/order/giao", _make_task_handler("giao"))
    r.add_post("/api/order/nop-tien", _make_task_handler("nop"))
    r.add_post("/api/order/task", api_task_handler)
    r.add_post("/api/order/refresh-view", api_refresh_handler)
    r.add_post("/api/order/fix", api_fix_handler)
    r.add_post("/api/order/invoice/update", api_invoice_update_handler)
    r.add_post("/api/order/assign-customer", api_assign_customer_handler)
    r.add_post("/api/order/ngay-giao", api_set_ngay_giao_handler)
    r.add_post("/api/order/invoice/create-kiotviet", api_create_invoice_handler)
    r.add_post("/api/order/invoice/delete-kiotviet", api_delete_invoice_handler)
    r.add_post("/api/order/refresh-debt", api_refresh_debt_handler)
    r.add_get("/api/order/{thread_id}/invoice-html", api_invoice_html_handler)
    r.add_post("/api/order/{thread_id}/invoice-image/ensure", api_ensure_invoice_image_handler)
    r.add_get("/api/products", products_search_handler)
    r.add_post("/api/products", product_create_handler)
    r.add_get("/api/products/kiotviet", product_kiotviet_search_handler)
    r.add_get("/api/kiotviet/categories", kiotviet_categories_handler)
    r.add_post("/api/products/{code}/kiotviet-create", product_kv_create_handler)
    r.add_post("/api/products/{code}/rename", product_rename_handler)
    r.add_post("/api/products/{code}/link", product_link_handler)
    r.add_post("/api/products/{code}/unlink", product_unlink_handler)
    r.add_delete("/api/products/{code}", product_delete_handler)
    r.add_post("/api/products/{code}", product_update_handler)
    r.add_get("/api/products/{product_code}/recipe", recipe_get_handler)
    r.add_post("/api/products/{product_code}/recipe", recipe_set_handler)
    r.add_delete("/api/products/{product_code}/recipe/{line_id}", recipe_delete_handler)
    r.add_post("/api/order/reply", api_reply_handler)
    r.add_post("/api/customer/price", api_customer_price_handler)
    r.add_post("/api/order/{id}/task_status/clear", api_task_status_clear_handler)
    r.add_post("/api/order/{id}/custom-task", add_custom_task_handler)
    r.add_post("/api/order/{id}/custom-task/remove", remove_custom_task_handler)
    r.add_post("/api/order/print-giao", api_print_giao_handler)
    r.add_post("/api/order/create", order_create_handler)
    r.add_get("/api/order/{thread_id}/history", order_history_handler)
    r.add_get("/api/order/{thread_id}/comments", comments_list_handler)
    r.add_post("/api/order/{thread_id}/comments", comments_add_handler)
    r.add_get("/api/order/{thread_id}/images", images_list_handler)
    r.add_post("/api/order/{thread_id}/images", images_upload_handler)
    r.add_delete("/api/order/{thread_id}/images/{image_id}", images_delete_handler)
    r.add_post("/api/order/{thread_id}/images/{image_id}/kind", images_kind_handler)
    r.add_get("/api/order/{thread_id}/images/{image_id}/comments", image_comments_list_handler)
    r.add_post("/api/order/{thread_id}/images/{image_id}/comments", image_comments_add_handler)
    r.add_delete("/api/order/{thread_id}/images/{image_id}/comments/{comment_id}", image_comments_delete_handler)
    r.add_get("/api/order/{thread_id}/images/{image_id}/file", images_file_handler)
    # ─── media dùng chung (comments+ảnh) cho production slip / box (web-only) ──
    r.add_get("/api/media/{scope}/{entity_id}/comments", em_comments_list)
    r.add_post("/api/media/{scope}/{entity_id}/comments", em_comments_add)
    r.add_get("/api/media/{scope}/{entity_id}/images", em_images_list)
    r.add_post("/api/media/{scope}/{entity_id}/images", em_images_upload)
    r.add_delete("/api/media/{scope}/{entity_id}/images/{image_id}", em_images_delete)
    r.add_get("/api/media/{scope}/{entity_id}/images/{image_id}/file", em_images_file)
    from server_app.entity_history import entity_history_handler
    r.add_get("/api/media/{scope}/{entity_id}/history", entity_history_handler)
    from server_app.activity import activity_handler
    r.add_get("/api/activity", activity_handler)
    # ─── VIỆC (task list — bảng tasks + mirror task đơn) ────────────────────
    from server_app.task_routes import (
        task_delete_handler, task_get_handler, task_update_handler,
        tasks_create_handler, tasks_list_handler,
    )
    from server_app.task_routes import task_assignees_handler
    r.add_get("/api/tasks/assignees", task_assignees_handler)   # TRƯỚC /{task_id}
    r.add_get("/api/tasks", tasks_list_handler)
    r.add_post("/api/tasks", tasks_create_handler)
    r.add_get("/api/tasks/{task_id}", task_get_handler)
    r.add_post("/api/tasks/{task_id}", task_update_handler)
    r.add_delete("/api/tasks/{task_id}", task_delete_handler)
    # ─── phiếu sản xuất (production) ─────────────────────────────────────────
    # catalog + create đăng ký TRƯỚC /{thread_id} để không bị route động nuốt
    r.add_get("/api/production/catalog", production_catalog_handler)
    r.add_get("/api/production", production_list_handler)
    r.add_post("/api/production", production_create_handler)
    from server_app.production_dashboard_routes import production_report_dashboard_handler, production_worker_report_handler
    r.add_get("/api/production/report-dashboard", production_report_dashboard_handler)  # TRƯỚC {thread_id}
    r.add_get("/api/production/worker/{name}", production_worker_report_handler)
    r.add_get("/api/production/{thread_id}", production_detail_handler)
    r.add_delete("/api/production/{thread_id}", production_delete_handler)
    r.add_post("/api/production/{thread_id}/product", production_set_product_handler)
    r.add_post("/api/production/{thread_id}/target", production_set_target_handler)
    r.add_post("/api/production/{thread_id}/note", production_set_note_handler)
    r.add_post("/api/production/{thread_id}/kind", production_set_kind_handler)
    r.add_post("/api/production/{thread_id}/slip-lock", production_slip_lock_handler)
    r.add_post("/api/production/{thread_id}/slip-unlock", production_slip_unlock_handler)
    r.add_post("/api/production/{thread_id}/number", production_add_number_handler)
    r.add_post("/api/production/{thread_id}/boxes", production_add_boxes_handler)
    r.add_get("/api/production/{thread_id}/boxes", production_boxes_list_handler)
    r.add_post("/api/production/{thread_id}/report/parse", production_report_parse_handler)
    r.add_post("/api/production/{thread_id}/report/lock", production_report_lock_handler)
    r.add_get("/api/production/{thread_id}/report/lock", production_report_lock_status_handler)
    r.add_post("/api/production/{thread_id}/report/unlock", production_report_unlock_handler)
    r.add_post("/api/production/{thread_id}/report/draft", production_report_draft_handler)
    r.add_post("/api/production/{thread_id}/report", production_report_save_handler)

    # ─── danh sách thợ (template báo cáo) ────────────────────────────────────
    from server_app.worker_routes import (
        workers_list_handler, workers_add_handler, workers_update_handler, workers_delete_handler,
        workers_reorder_handler,
    )
    r.add_get("/api/workers", workers_list_handler)
    r.add_post("/api/workers", workers_add_handler)
    r.add_post("/api/workers/reorder", workers_reorder_handler)   # TRƯỚC {id} kẻo bị nuốt
    r.add_post("/api/workers/{id}", workers_update_handler)
    r.add_delete("/api/workers/{id}", workers_delete_handler)
    # ─── kho thùng (inventory) ───────────────────────────────────────────────
    r.add_get("/api/inventory", inventory_list_handler)
    r.add_get("/api/inventory/boxes", all_boxes_handler)
    r.add_get("/api/inventory/unplaced-count", unplaced_count_handler)
    from server_app.stock_demand import stock_demand_handler
    r.add_get("/api/inventory/demand", stock_demand_handler)
    r.add_get("/api/banner/pins", banner_pins_handler)
    r.add_post("/api/banner/pin", banner_pin_create_handler)
    r.add_delete("/api/banner/pin/{pin_id}", banner_pin_delete_handler)
    r.add_get("/api/places", places_list_handler)
    from server_app.place_timeline import place_timeline_handler
    r.add_get("/api/places/{place_id}/timeline", place_timeline_handler)
    r.add_post("/api/places", place_create_handler)
    r.add_post("/api/places/{place_id}", place_rename_handler)
    r.add_delete("/api/places/{place_id}", place_delete_handler)
    r.add_get("/api/units", units_list_handler)
    r.add_post("/api/units", unit_create_handler)
    r.add_delete("/api/units/{unit_id}", unit_delete_handler)
    r.add_get("/api/inventory/box/{box_id}", box_detail_handler)
    r.add_post("/api/inventory/box/{box_id}", box_update_handler)
    r.add_delete("/api/inventory/box/{box_id}", box_delete_handler)
    r.add_post("/api/inventory/box/{box_id}/transfer", box_transfer_handler)
    r.add_post("/api/inventory/box/{box_id}/disable", box_disable_handler)
    r.add_get("/api/inventory/{product_code}/orders", product_orders_handler)
    r.add_get("/api/inventory/{product_code}", inventory_detail_handler)
    r.add_get("/api/order/{thread_id}/allocations", order_allocations_handler)
    r.add_post("/api/order/{thread_id}/allocate", order_allocate_handler)
    r.add_post("/api/order/{thread_id}/release", order_release_handler)
    from server_app.order_stock_lock import order_stock_confirm_handler
    r.add_post("/api/order/{thread_id}/stock-confirm", order_stock_confirm_handler)
    from server_app.return_routes import (returns_list_handler, returns_create_handler,
                                          returns_delete_handler, returns_all_handler, return_detail_handler)
    r.add_get("/api/customers/{key}/returns", returns_list_handler)
    r.add_post("/api/customers/{key}/returns", returns_create_handler)
    r.add_get("/api/returns", returns_all_handler)
    r.add_get("/api/returns/{id}", return_detail_handler)
    r.add_post("/api/returns/{id}/delete", returns_delete_handler)
    from server_app.return_routes import return_update_handler, return_invoice_handler
    r.add_post("/api/returns/{id}/update", return_update_handler)
    r.add_post("/api/returns/{id}/invoice", return_invoice_handler)
    from server_app.return_routes import return_invoice_delete_handler
    r.add_post("/api/returns/{id}/delete-invoice", return_invoice_delete_handler)
    from server_app.settings_routes import settings_get_handler, settings_set_handler
    r.add_get("/api/settings", settings_get_handler)
    r.add_post("/api/settings", settings_set_handler)

    # ─── notification center ─────────────────────────────────────────────────
    from server_app.notify import notifications_list_handler
    r.add_get("/api/notifications", notifications_list_handler)
    # ─── quản lý user (chỉ admin) ────────────────────────────────────────────
    r.add_get("/api/users", users_list_handler)
    r.add_post("/api/users", users_create_handler)
    r.add_post("/api/users/{username}/role", users_role_handler)
    r.add_post("/api/users/{username}/disabled", users_disabled_handler)
    r.add_post("/api/users/{username}/pin", users_pin_handler)
    # ─── sổ quỹ (cash book) ──────────────────────────────────────────────────
    r.add_get("/api/quy", quy_list_handler)
    r.add_post("/api/quy", quy_create_handler)
    r.add_get("/api/quy/{id}", quy_detail_handler)
    r.add_delete("/api/quy/{id}", quy_delete_handler)
    r.add_get("/api/customers", customers_search_handler)
    r.add_get("/api/customers/kiotviet", customer_kv_search_handler)   # TRƯỚC {key} GET
    from server_app.customer_create import customer_create_handler
    r.add_post("/api/customers/new", customer_create_handler)   # TRƯỚC {key} POST
    r.add_post("/api/customers/{key}/link-kiotviet", customer_kv_link_handler)
    r.add_post("/api/customers/{key}/unlink-kiotviet", customer_kv_unlink_handler)
    r.add_get("/api/customers/{key}", customer_detail_handler)
    r.add_post("/api/customers/{key}", customer_update_handler)
    r.add_delete("/api/customers/{key}", customer_delete_handler)
    r.add_get("/api/customers/{key}/orders", customer_orders_handler)
    r.add_get("/api/customers/{key}/feed", customer_feed_handler)
    r.add_post("/api/customers/{key}/refresh-debt", customer_refresh_debt_handler)
    r.add_get("/api/price-lists", price_lists_handler)
    r.add_get("/api/price-lists/{id}", price_list_detail_handler)
    r.add_post("/api/price-lists/{id}", price_list_save_handler)
    r.add_post("/api/price-lists/{id}/price", price_one_save_handler)
    r.add_get("/api/price-lists/{id}/history", price_list_history_handler)

    async def _reminder_stop_handler(request: web.Request):
        from nop_tien_reminder import stop_reminder
        thread_id_str = request.match_info.get("id", "")
        try:
            stop_reminder(int(thread_id_str))
            return web.json_response({"ok": True})
        except (ValueError, TypeError):
            return web.json_response({"ok": False, "error": "invalid thread_id"}, status=400)
    r.add_post("/api/reminder/stop/{id}", _reminder_stop_handler)

    return app
