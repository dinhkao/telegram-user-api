"""user_store — bảng `web_users` trong app.db: tài khoản đăng nhập web app.

Ai dùng: server_app/web_auth (login), tools/add_web_user.py (quản lý user).
Layering: pin.py (thuần, unit-test) → schema.py (bảng) → users.py (IO).
"""
from user_store.users import (
    add_user, get_user, list_users, rename_user, set_disabled, set_pin, set_role,
    verify_login, is_office, ROLES, OFFICE_ROLES,
)

__all__ = [
    "add_user", "get_user", "list_users", "rename_user", "set_disabled", "set_pin", "set_role",
    "verify_login", "is_office", "ROLES", "OFFICE_ROLES",
]
