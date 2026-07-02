"""CLI quản lý user web app (bảng web_users trong app.db).

Dùng:
  .venv/bin/python tools/add_web_user.py add <username> [--name "Tên"] [--role staff|admin]
  .venv/bin/python tools/add_web_user.py list
  .venv/bin/python tools/add_web_user.py disable <username>
  .venv/bin/python tools/add_web_user.py enable <username>

PIN nhập ẩn qua getpass (không lộ trong shell history). Connects to: user_store.
"""
from __future__ import annotations

import argparse
import getpass
import sys

sys.path.insert(0, ".")

from user_store import add_user, list_users, set_disabled


def main() -> int:
    parser = argparse.ArgumentParser(description="Quản lý user web app")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_add = sub.add_parser("add")
    p_add.add_argument("username")
    p_add.add_argument("--name", default="")
    p_add.add_argument("--role", default="staff", choices=["staff", "admin"])
    sub.add_parser("list")
    for name in ("disable", "enable"):
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
    else:
        changed = set_disabled(args.username, args.cmd == "disable")
        print("OK" if changed else f"Không thấy user '{args.username}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
