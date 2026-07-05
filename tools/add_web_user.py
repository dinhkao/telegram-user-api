"""CLI quản lý user web app (bảng web_users trong app.db).

Dùng:
  .venv/bin/python tools/add_web_user.py add <username> [--name "Tên"] [--role staff|van_phong|admin]
  .venv/bin/python tools/add_web_user.py pin <username>      # đổi PIN
  .venv/bin/python tools/add_web_user.py role <username> <staff|van_phong|admin>
  .venv/bin/python tools/add_web_user.py list
  .venv/bin/python tools/add_web_user.py disable <username>
  .venv/bin/python tools/add_web_user.py enable <username>

Vai trò: admin (toàn quyền) ⊃ van_phong (văn phòng: nhận tiền + tạo thanh toán) ⊃
staff (nhân viên). PIN nhập ẩn qua getpass. Connects to: user_store.
"""
from __future__ import annotations

import argparse
import getpass
import sys

sys.path.insert(0, ".")

from user_store import ROLES, add_user, list_users, set_disabled, set_pin, set_role


def main() -> int:
    parser = argparse.ArgumentParser(description="Quản lý user web app")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_add = sub.add_parser("add")
    p_add.add_argument("username")
    p_add.add_argument("--name", default="")
    p_add.add_argument("--role", default="staff", choices=list(ROLES))
    p_role = sub.add_parser("role")
    p_role.add_argument("username")
    p_role.add_argument("role", choices=list(ROLES))
    sub.add_parser("list")
    for name in ("pin", "disable", "enable"):
        p = sub.add_parser(name)
        p.add_argument("username")
    args = parser.parse_args()

    if args.cmd == "add":
        pin = getpass.getpass("PIN: ")
        pin2 = getpass.getpass("Nhập lại PIN: ")
        if pin != pin2:
            print("PIN không khớp", file=sys.stderr)
            return 1
        try:
            user = add_user(args.username, pin, display_name=args.name, role=args.role)
        except ValueError as exc:
            print(f"Lỗi: {exc}", file=sys.stderr)
            return 1
        print(f"Đã tạo: {user['username']} ({user['display_name']}, {user['role']})")
    elif args.cmd == "list":
        for u in list_users():
            flag = " [KHOÁ]" if u["disabled"] else ""
            print(f"{u['username']}\t{u['display_name']}\t{u['role']}{flag}")
    elif args.cmd == "pin":
        pin = getpass.getpass("PIN mới: ")
        pin2 = getpass.getpass("Nhập lại: ")
        if pin != pin2:
            print("PIN không khớp", file=sys.stderr)
            return 1
        print("OK" if set_pin(args.username, pin) else f"Không thấy user '{args.username}'")
    elif args.cmd == "role":
        print(f"OK → {args.role}" if set_role(args.username, args.role) else f"Không thấy user '{args.username}'")
    else:
        changed = set_disabled(args.username, args.cmd == "disable")
        print("OK" if changed else f"Không thấy user '{args.username}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
