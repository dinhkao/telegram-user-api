"""web_auth — đăng nhập + chặn API cho web app quản lý đơn (per-user, token HMAC).

- token.py      : ký/kiểm token (thuần, unit-test)
- secret.py     : nguồn secret ký token (env → file cạnh app.db)
- middleware.py : aiohttp middleware — gắn request["web_user"], chặn /api/* khi bật
- routes.py     : POST /api/auth/login, GET /api/auth/me

Bật enforcement qua env WEB_AUTH_ENABLED=true (mặc định TẮT — không phá UI cũ).
Token luôn được đọc nếu client gửi (attribution chạy trước cả khi bật chặn).
Connects to: user_store (verify login), server_app/app_factory (đăng ký).
"""
from server_app.web_auth.middleware import web_auth_middleware
from server_app.web_auth.routes import login_handler, me_handler

__all__ = ["web_auth_middleware", "login_handler", "me_handler"]
