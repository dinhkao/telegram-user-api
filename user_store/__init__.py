"""user_store — bảng `web_users` trong app.db: tài khoản đăng nhập web app.

Ai dùng: server_app/web_auth (login), tools/add_web_user.py (quản lý user).
Layering: pin.py (thuần, unit-test) → schema.py (bảng) → users.py (IO).
"""
from user_store.users import add_user, get_user, list_users, set_disabled, verify_login

__all__ = ["add_user", "get_user", "list_users", "set_disabled", "verify_login"]
