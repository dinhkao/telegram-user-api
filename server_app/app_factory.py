from __future__ import annotations

from aiohttp import web

from server_app.audit import audit_middleware
from server_app.config import PORT
from server_app.cors import cors_middleware
from server_app.comment_routes import comments_add_handler, comments_list_handler
from server_app.customer_routes import customer_detail_handler, customer_refresh_debt_handler, customers_search_handler
from server_app.donhang_routes import donhang_handler, donhang_msg_handler, donhang_page_handler, donhang_stats_handler
from server_app.image_routes import images_delete_handler, images_file_handler, images_list_handler, images_upload_handler
from server_app.order_api_auto import auto_parse_handler, order_preview_handler, customer_price_list_handler
from server_app.order_api_create import order_create_handler
from server_app.order_api_mutations import api_assign_customer_handler, api_fix_handler, api_invoice_update_handler, api_refresh_handler, api_reply_handler
from server_app.order_api_payments import api_customer_price_handler, order_totals_handler, payment_ck_handler, payment_delete_handler, payment_tm_handler
from server_app.order_api_print import api_print_giao_handler
from server_app.order_api_tasks import _make_task_handler, api_task_handler, api_task_status_clear_handler
from server_app.order_api_invoice import api_create_invoice_handler, api_delete_invoice_handler, api_invoice_html_handler, api_refresh_debt_handler
from server_app.order_history import order_history_handler
from server_app.orders_api import order_detail_handler, orders_api_handler
from server_app.product_routes import products_search_handler
from server_app.production_routes import (
    production_add_number_handler,
    production_catalog_handler,
    production_create_handler,
    production_delete_handler,
    production_detail_handler,
    production_list_handler,
    production_set_note_handler,
    production_report_parse_handler,
    production_report_save_handler,
    production_set_product_handler,
    production_set_target_handler,
)
from server_app.inventory_routes import (
    production_add_boxes_handler,
    production_boxes_list_handler,
    inventory_list_handler,
    inventory_detail_handler,
    box_detail_handler,
    box_update_handler,
    box_disable_handler,
    order_allocations_handler,
    order_allocate_handler,
    order_release_handler,
)
from server_app.orders_pages import order_detail_page_handler, orders_page_handler
from server_app.web_auth import login_handler, me_handler, web_auth_middleware
from server_app.web_pages import index_handler
from server_app.webapp_routes import register_webapp_routes
from server_app.websocket_routes import websocket_handler
from server_app import state


def create_app():
    from tg_edit import make_handler as make_edit_handler
    from tg_send import make_handler as make_send_handler
    from tg_send_file import make_handler as make_send_file_handler

    app = web.Application(middlewares=[cors_middleware, audit_middleware, web_auth_middleware])
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
    r.add_get("/api/order/{thread_id}", order_detail_handler)
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
    r.add_post("/api/order/invoice/create-kiotviet", api_create_invoice_handler)
    r.add_post("/api/order/invoice/delete-kiotviet", api_delete_invoice_handler)
    r.add_post("/api/order/refresh-debt", api_refresh_debt_handler)
    r.add_get("/api/order/{thread_id}/invoice-html", api_invoice_html_handler)
    r.add_get("/api/products", products_search_handler)
    r.add_post("/api/order/reply", api_reply_handler)
    r.add_post("/api/customer/price", api_customer_price_handler)
    r.add_post("/api/order/{id}/task_status/clear", api_task_status_clear_handler)
    r.add_post("/api/order/print-giao", api_print_giao_handler)
    r.add_post("/api/order/create", order_create_handler)
    r.add_get("/api/order/{thread_id}/history", order_history_handler)
    r.add_get("/api/order/{thread_id}/comments", comments_list_handler)
    r.add_post("/api/order/{thread_id}/comments", comments_add_handler)
    r.add_get("/api/order/{thread_id}/images", images_list_handler)
    r.add_post("/api/order/{thread_id}/images", images_upload_handler)
    r.add_delete("/api/order/{thread_id}/images/{image_id}", images_delete_handler)
    r.add_get("/api/order/{thread_id}/images/{image_id}/file", images_file_handler)
    # ─── phiếu sản xuất (production) ─────────────────────────────────────────
    # catalog + create đăng ký TRƯỚC /{thread_id} để không bị route động nuốt
    r.add_get("/api/production/catalog", production_catalog_handler)
    r.add_get("/api/production", production_list_handler)
    r.add_post("/api/production", production_create_handler)
    r.add_get("/api/production/{thread_id}", production_detail_handler)
    r.add_delete("/api/production/{thread_id}", production_delete_handler)
    r.add_post("/api/production/{thread_id}/product", production_set_product_handler)
    r.add_post("/api/production/{thread_id}/target", production_set_target_handler)
    r.add_post("/api/production/{thread_id}/note", production_set_note_handler)
    r.add_post("/api/production/{thread_id}/number", production_add_number_handler)
    r.add_post("/api/production/{thread_id}/boxes", production_add_boxes_handler)
    r.add_get("/api/production/{thread_id}/boxes", production_boxes_list_handler)
    r.add_post("/api/production/{thread_id}/report/parse", production_report_parse_handler)
    r.add_post("/api/production/{thread_id}/report", production_report_save_handler)
    # ─── kho thùng (inventory) ───────────────────────────────────────────────
    r.add_get("/api/inventory", inventory_list_handler)
    r.add_get("/api/inventory/box/{box_id}", box_detail_handler)
    r.add_post("/api/inventory/box/{box_id}", box_update_handler)
    r.add_post("/api/inventory/box/{box_id}/disable", box_disable_handler)
    r.add_get("/api/inventory/{product_code}", inventory_detail_handler)
    r.add_get("/api/order/{thread_id}/allocations", order_allocations_handler)
    r.add_post("/api/order/{thread_id}/allocate", order_allocate_handler)
    r.add_post("/api/order/{thread_id}/release", order_release_handler)

    r.add_get("/api/customers", customers_search_handler)
    r.add_get("/api/customers/{key}", customer_detail_handler)
    r.add_post("/api/customers/{key}/refresh-debt", customer_refresh_debt_handler)

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
