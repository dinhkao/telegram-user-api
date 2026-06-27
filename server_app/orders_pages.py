from __future__ import annotations

from aiohttp import web


async def orders_page_handler(request: web.Request):
    return web.FileResponse("static/orders.html")


async def order_detail_page_handler(request: web.Request):
    return web.FileResponse("static/order-detail.html")
