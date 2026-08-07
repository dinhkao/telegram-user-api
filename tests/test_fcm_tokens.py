"""Test bảng `fcm_tokens` (notif_store.fcm_tokens): upsert theo token (máy đổi người
đăng nhập), eligible_tokens loại vai trò bó hẹp + user bị khoá + username không còn
trong web_users, và delete_tokens (dọn token chết). Không đụng firebase."""
from __future__ import annotations

import os
import tempfile
import unittest

from notif_store.fcm_tokens import delete_tokens, eligible_tokens, ensure_table, register_token
from user_store.schema import _CREATE_SQL as USERS_SQL
from utils.db import get_connection


class FcmTokensTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = get_connection(self.path)
        self.conn.execute(USERS_SQL)
        ensure_table(self.conn)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.path)

    def _user(self, username: str, role: str = "staff", disabled: int = 0):
        self.conn.execute(
            "INSERT INTO web_users (username, pin_hash, display_name, role, disabled, created_at) "
            "VALUES (?, 'x', ?, ?, ?, 0)",
            (username, username, role, disabled),
        )

    def _rows(self):
        return {r[0]: r[1] for r in self.conn.execute("SELECT token, username FROM fcm_tokens")}

    # ── upsert ───────────────────────────────────────────────────────────────
    def test_register_upsert_doi_username(self):
        register_token(self.conn, "tokA", "duy")
        register_token(self.conn, "tokA", "lan")     # máy đó đổi người đăng nhập
        self.assertEqual(self._rows(), {"tokA": "lan"})

    def test_register_nhieu_token_cua_1_user(self):
        register_token(self.conn, "tokA", "duy")
        register_token(self.conn, "tokB", "duy")
        self.assertEqual(self._rows(), {"tokA": "duy", "tokB": "duy"})

    # ── lọc người nhận ───────────────────────────────────────────────────────
    def test_eligible_loai_chat_luong_disabled_va_user_da_xoa(self):
        self._user("duy", role="admin")
        self._user("lan", role="staff")
        self._user("cl", role="chat_luong")
        self._user("nghi", role="staff", disabled=1)
        for u in ("duy", "lan", "cl", "nghi"):
            register_token(self.conn, f"tok_{u}", u)
        register_token(self.conn, "tok_ma", "khong_ton_tai")   # user đã bị xoá

        self.assertEqual(sorted(eligible_tokens(self.conn)), ["tok_duy", "tok_lan"])

    def test_eligible_exclude_roles_rong_thi_lay_ca_chat_luong(self):
        self._user("duy")
        self._user("cl", role="chat_luong")
        register_token(self.conn, "tok_duy", "duy")
        register_token(self.conn, "tok_cl", "cl")
        self.assertEqual(sorted(eligible_tokens(self.conn, exclude_roles=())),
                         ["tok_cl", "tok_duy"])

    def test_eligible_rong_khi_chua_ai_dang_ky(self):
        self._user("duy")
        self.assertEqual(eligible_tokens(self.conn), [])

    # ── dọn token chết ───────────────────────────────────────────────────────
    def test_delete_tokens(self):
        self._user("duy")
        register_token(self.conn, "tokA", "duy")
        register_token(self.conn, "tokB", "duy")
        self.assertEqual(delete_tokens(self.conn, ["tokA", "khong_co"]), 1)
        self.assertEqual(list(self._rows()), ["tokB"])
        self.assertEqual(delete_tokens(self.conn, []), 0)
        self.assertEqual(delete_tokens(self.conn, None), 0)


if __name__ == "__main__":
    unittest.main()
