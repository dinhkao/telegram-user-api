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
from server_app.order_api_mutations import api_assign_customer_handler, api_fix_handler, api_invoice_update_handler, api_refresh_handler, api_reply_handler, api_set_bypass_debt_handler, api_set_ngay_giao_handler, api_set_no_track_handler
from server_app.order_api_payments import api_customer_price_handler, order_totals_handler, payment_ck_handler, payment_delete_handler, payment_tm_handler
from server_app.order_api_debt_suggest import api_debt_suggest_handler
from server_app.order_api_bulk_payment import bulk_payment_handler, payment_context_handler
from server_app.order_api_print import api_print_giao_handler
from server_app.order_api_tasks import _make_task_handler, api_task_handler, api_task_status_clear_handler
from server_app.order_api_custom_tasks import add_custom_task_handler, remove_custom_task_handler
from server_app.order_api_invoice import api_create_invoice_handler, api_delete_invoice_handler, api_ensure_invoice_image_handler, api_invoice_html_handler, api_refresh_debt_handler, api_set_invoice_reference_image_handler
from server_app.order_history import order_history_handler
from server_app.orders_api import order_detail_handler, orders_api_handler, orders_delivery_handler, orders_delivering_handler
from server_app.product_routes import (
    products_search_handler, product_create_handler, product_kiotviet_search_handler,
    product_link_handler, product_unlink_handler, product_delete_handler, product_update_handler, product_rename_handler,
    product_kv_create_handler, kiotviet_categories_handler,
)
from server_app.product_unit_routes import register as register_product_unit_routes
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
    bulk_move_handler,
    box_delete_handler,
    box_transfer_handler,
    box_return_material_handler,
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
from server_app.cloudinary_routes import camera_images_handler, stop_camera_cache, warm_camera_cache
from server_app.usage_routes import usage_batch_handler, usage_stats_handler
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
    app.on_startup.append(warm_camera_cache)
    app.on_cleanup.append(stop_camera_cache)
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
    r.add_get("/api/orders/delivering", orders_delivering_handler)
    r.add_get("/api/cloudinary/camera-images", camera_images_handler)
    r.add_post("/api/usage/batch", usage_batch_handler)
    r.add_get("/api/usage/stats", usage_stats_handler)
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
    r.add_post("/api/order/payment/bulk", bulk_payment_handler)
    from server_app.order_api_collect import debtors_handler, collect_batch_handler
    r.add_get("/api/collect/debtors", debtors_handler)          # thu tiền hàng loạt nhiều khách
    r.add_post("/api/collect/batch", collect_batch_handler)
    r.add_get("/api/order/{thread_id}/payment-context", payment_context_handler)
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
    r.add_post("/api/order/no-track", api_set_no_track_handler)
    r.add_get("/api/order/{thread_id}/debt-suggest", api_debt_suggest_handler)
    r.add_post("/api/order/bypass-debt", api_set_bypass_debt_handler)
    r.add_post("/api/order/invoice/create-kiotviet", api_create_invoice_handler)
    r.add_post("/api/order/invoice/delete-kiotviet", api_delete_invoice_handler)
    r.add_post("/api/order/invoice/reference-image", api_set_invoice_reference_image_handler)
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
    register_product_unit_routes(r)   # /api/products/{code}/units* — quy đổi đơn vị
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
    from server_app.order_timeline import order_timeline_handler
    r.add_get("/api/order/{thread_id}/timeline", order_timeline_handler)
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
    from server_app.production_dashboard_routes import production_report_dashboard_handler, production_worker_report_handler, production_payslips_html_handler
    r.add_get("/api/production/report-dashboard", production_report_dashboard_handler)  # TRƯỚC {thread_id}
    r.add_get("/api/production/payslips-html", production_payslips_html_handler)  # HTML in phiếu lương nhiều thợ
    r.add_get("/api/production/worker/{name}", production_worker_report_handler)
    from server_app.production_wages import wages_dashboard_handler
    r.add_get("/api/production/wages", wages_dashboard_handler)   # TIỀN CÔNG (office-only) — TRƯỚC {thread_id}
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
    from server_app.production_wages import phieu_wages_handler, set_allowance_handler, set_slip_wage_handler
    r.add_get("/api/production/{thread_id}/wages", phieu_wages_handler)          # tiền + phụ cấp (office)
    r.add_post("/api/production/{thread_id}/allowance", set_allowance_handler)   # đặt phụ cấp (office)
    r.add_post("/api/production/{thread_id}/wage", set_slip_wage_handler)        # chốt đơn giá lương phiếu (office)

    # ─── bảng lương SP (office-only) ─────────────────────────────────────────
    from server_app.wage_routes import wages_list_handler, wages_set_handler
    r.add_get("/api/wages", wages_list_handler)
    r.add_post("/api/wages", wages_set_handler)

    # ─── phiếu báo cáo SX (office-only — tiền lương) ─────────────────────────
    from server_app.report_slip_routes import (
        report_slips_list_handler, report_slips_create_handler,
        report_slip_detail_handler, report_slip_update_handler, report_slip_delete_handler,
    )
    r.add_get("/api/report-slips", report_slips_list_handler)
    r.add_post("/api/report-slips", report_slips_create_handler)
    r.add_get("/api/report-slips/{id}", report_slip_detail_handler)
    r.add_post("/api/report-slips/{id}", report_slip_update_handler)
    r.add_delete("/api/report-slips/{id}", report_slip_delete_handler)

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
    # ─── bảng lương tháng (office only) ──────────────────────────────────────
    from server_app.payroll_routes import (
        payroll_month_handler, payroll_advances_handler, payroll_adjust_handler,
        payroll_advance_add_handler, payroll_advance_delete_handler,
    )
    r.add_get("/api/payroll/month", payroll_month_handler)
    r.add_get("/api/payroll/advances", payroll_advances_handler)
    r.add_post("/api/payroll/adjust", payroll_adjust_handler)
    r.add_post("/api/payroll/advance", payroll_advance_add_handler)   # TRƯỚC {id}
    r.add_delete("/api/payroll/advance/{id}", payroll_advance_delete_handler)
    # ─── kho thùng (inventory) ───────────────────────────────────────────────
    r.add_get("/api/inventory", inventory_list_handler)
    r.add_get("/api/inventory/boxes", all_boxes_handler)
    r.add_get("/api/inventory/unplaced-count", unplaced_count_handler)
    from server_app.stock_demand import stock_demand_handler
    r.add_get("/api/inventory/demand", stock_demand_handler)
    from server_app.inventory_call_map import call_map_handler
    r.add_get("/api/inventory/call-numbers", call_map_handler)
    from server_app.aux_loss_routes import aux_loss_handler   # TRƯỚC {code} — dashboard hao hụt NL phụ
    r.add_get("/api/inventory/aux-loss", aux_loss_handler)
    from server_app.product_timeline import product_timeline_handler
    r.add_get("/api/inventory/{code}/timeline", product_timeline_handler)
    r.add_get("/api/banner/pins", banner_pins_handler)
    r.add_post("/api/banner/pin", banner_pin_create_handler)
    r.add_delete("/api/banner/pin/{pin_id}", banner_pin_delete_handler)
    r.add_get("/api/places", places_list_handler)
    from server_app.place_timeline import place_timeline_handler
    r.add_get("/api/places/{place_id}/timeline", place_timeline_handler)
    from server_app.stocktake_routes import (
        place_stocktakes_handler, stocktake_create_handler, stocktake_detail_handler,
        stocktake_save_handler, stocktake_complete_handler, stocktake_lock_handler,
        stocktake_unlock_handler, stocktake_resync_handler, stocktake_void_handler,
        stocktake_apply_handler,
    )
    r.add_get("/api/places/{place_id}/stocktakes", place_stocktakes_handler)
    r.add_post("/api/places/{place_id}/stocktakes", stocktake_create_handler)
    r.add_get("/api/stocktakes/{stocktake_id}", stocktake_detail_handler)
    r.add_post("/api/stocktakes/{stocktake_id}", stocktake_save_handler)
    r.add_post("/api/stocktakes/{stocktake_id}/complete", stocktake_complete_handler)
    r.add_post("/api/stocktakes/{stocktake_id}/resync", stocktake_resync_handler)
    r.add_post("/api/stocktakes/{stocktake_id}/apply", stocktake_apply_handler)   # áp chênh lệch vào kho
    r.add_post("/api/stocktakes/{stocktake_id}/void", stocktake_void_handler)
    r.add_post("/api/stocktakes/{stocktake_id}/lock", stocktake_lock_handler)
    r.add_post("/api/stocktakes/{stocktake_id}/unlock", stocktake_unlock_handler)
    r.add_post("/api/places", place_create_handler)
    r.add_post("/api/places/{place_id}", place_rename_handler)
    r.add_delete("/api/places/{place_id}", place_delete_handler)
    r.add_get("/api/units", units_list_handler)
    r.add_post("/api/units", unit_create_handler)
    r.add_delete("/api/units/{unit_id}", unit_delete_handler)
    from server_app.box_timeline import box_timeline_handler
    r.add_get("/api/inventory/box/{box_id}/timeline", box_timeline_handler)
    r.add_get("/api/inventory/box/{box_id}", box_detail_handler)
    r.add_post("/api/inventory/box/{box_id}", box_update_handler)
    r.add_delete("/api/inventory/box/{box_id}", box_delete_handler)
    from server_app.adjustment_routes import register as register_adjustment_routes
    register_adjustment_routes(r)   # /api/inventory/box/{id}/adjust + /api/adjustments* — phiếu điều chỉnh tồn
    r.add_post("/api/inventory/box/{box_id}/transfer", box_transfer_handler)
    r.add_post("/api/inventory/box/{box_id}/return-material", box_return_material_handler)
    r.add_post("/api/inventory/box/{box_id}/disable", box_disable_handler)
    r.add_post("/api/inventory/bulk-move", bulk_move_handler)   # chuyển kho hàng loạt
    r.add_get("/api/inventory/{product_code}/orders", product_orders_handler)
    r.add_get("/api/inventory/{product_code}", inventory_detail_handler)
    r.add_get("/api/order/{thread_id}/allocations", order_allocations_handler)
    r.add_post("/api/order/{thread_id}/allocate", order_allocate_handler)
    r.add_post("/api/order/{thread_id}/release", order_release_handler)
    from server_app.order_stock_lock import order_stock_confirm_handler
    r.add_post("/api/order/{thread_id}/stock-confirm", order_stock_confirm_handler)
    from server_app.stock_pick_lock import (stock_pick_lock_handler, stock_pick_lock_status_handler,
                                            stock_pick_unlock_handler)
    r.add_post("/api/order/{thread_id}/stock-pick/lock", stock_pick_lock_handler)
    r.add_get("/api/order/{thread_id}/stock-pick/lock", stock_pick_lock_status_handler)
    r.add_post("/api/order/{thread_id}/stock-pick/unlock", stock_pick_unlock_handler)
    from server_app.invoice_edit_lock import (invoice_edit_lock_handler, invoice_edit_lock_status_handler,
                                              invoice_edit_unlock_handler)
    r.add_post("/api/order/{thread_id}/invoice-edit/lock", invoice_edit_lock_handler)
    r.add_get("/api/order/{thread_id}/invoice-edit/lock", invoice_edit_lock_status_handler)
    r.add_post("/api/order/{thread_id}/invoice-edit/unlock", invoice_edit_unlock_handler)
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
    from server_app.return_routes import return_handle_goods_handler
    r.add_post("/api/returns/{id}/handle-goods", return_handle_goods_handler)
    # Nhập hàng + nhà cung cấp (100% local, không KiotViet)
    from server_app.supplier_routes import (suppliers_list_handler, supplier_create_handler,
                                            supplier_detail_handler, supplier_update_handler,
                                            supplier_delete_handler)
    r.add_get("/api/suppliers", suppliers_list_handler)
    r.add_post("/api/suppliers", supplier_create_handler)
    r.add_get("/api/suppliers/{id}", supplier_detail_handler)
    r.add_post("/api/suppliers/{id}", supplier_update_handler)
    r.add_post("/api/suppliers/{id}/delete", supplier_delete_handler)
    from server_app.purchase_routes import (purchases_all_handler, purchase_create_handler,
                                            purchase_detail_handler, purchase_update_handler,
                                            purchase_delete_handler, purchase_pay_handler,
                                            purchase_payment_delete_handler)
    r.add_get("/api/purchases", purchases_all_handler)
    r.add_post("/api/purchases", purchase_create_handler)
    r.add_get("/api/purchases/{id}", purchase_detail_handler)
    r.add_post("/api/purchases/{id}/update", purchase_update_handler)
    r.add_post("/api/purchases/{id}/delete", purchase_delete_handler)
    r.add_post("/api/purchases/{id}/pay", purchase_pay_handler)                 # trả NCC từ két
    r.add_post("/api/purchases/{id}/payments/{pid}/delete", purchase_payment_delete_handler)  # admin
    from server_app.purchase_goods_routes import (purchase_receive_goods_handler,
                                                  purchase_confirm_goods_handler,
                                                  purchase_unreceive_handler,
                                                  purchase_undo_goods_handler)
    r.add_post("/api/purchases/{id}/receive-goods", purchase_receive_goods_handler)  # ghi nhập từng đợt
    r.add_post("/api/purchases/{id}/confirm-goods", purchase_confirm_goods_handler)  # chốt nhập kho
    r.add_post("/api/purchases/{id}/unreceive", purchase_unreceive_handler)          # gỡ 1 dòng cộng thùng
    r.add_post("/api/purchases/{id}/undo-goods", purchase_undo_goods_handler)      # hủy chốt nhập kho (admin)
    from server_app.disposal_routes import (disposal_create_handler, disposal_delete_handler,
                                            disposal_detail_handler, disposals_all_handler)
    r.add_get("/api/disposals", disposals_all_handler)
    r.add_post("/api/disposals", disposal_create_handler)          # văn phòng
    r.add_get("/api/disposals/{id}", disposal_detail_handler)
    r.add_post("/api/disposals/{id}/delete", disposal_delete_handler)  # admin, hoàn tồn
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
    # ─── két tiền — ai đang giữ tiền (derive từ blob đơn) ────────────────────
    from server_app.cashbox_routes import (cashbox_summary_handler, cashbox_timeline_handler,
                                           cashbox_transfer_delete_handler, cashbox_transfer_handler,
                                           cashbox_withdraw_handler)
    r.add_get("/api/cashbox", cashbox_summary_handler)
    r.add_post("/api/cashbox/transfer", cashbox_transfer_handler)              # văn phòng — TRƯỚC {key}
    r.add_post("/api/cashbox/withdraw", cashbox_withdraw_handler)              # văn phòng — TRƯỚC {key}
    r.add_post("/api/cashbox/transfer/{id}/delete", cashbox_transfer_delete_handler)  # admin
    r.add_get("/api/cashbox/{key}/timeline", cashbox_timeline_handler)
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
