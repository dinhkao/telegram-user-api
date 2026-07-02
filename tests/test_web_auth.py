"""Unit tests thuần cho web_auth: PIN hash (user_store.pin), token HMAC
(web_auth.token), luật miễn chặn (web_auth.middleware.is_exempt/extract_token).
Không DB, không aiohttp server.
"""
from __future__ import annotations

import unittest

from server_app.web_auth.middleware import extract_token, is_exempt
from server_app.web_auth.token import issue_token, verify_token
from user_store.pin import hash_pin, verify_pin


class PinHash(unittest.TestCase):
    def test_roundtrip(self):
        stored = hash_pin("1234")
        self.assertTrue(verify_pin("1234", stored))

    def test_wrong_pin(self):
        self.assertFalse(verify_pin("9999", hash_pin("1234")))

    def test_salt_differs(self):
        self.assertNotEqual(hash_pin("1234"), hash_pin("1234"))

    def test_garbage_stored_returns_false(self):
        self.assertFalse(verify_pin("1234", "not-a-hash"))
        self.assertFalse(verify_pin("1234", ""))

    def test_unicode_pin(self):
        stored = hash_pin("mật khẩu")
        self.assertTrue(verify_pin("mật khẩu", stored))


class Token(unittest.TestCase):
    SECRET = "s3cret"

    def test_roundtrip(self):
        tok = issue_token(self.SECRET, "duy", ttl_seconds=60, now=1000)
        self.assertEqual(verify_token(self.SECRET, tok, now=1030), "duy")

    def test_expired(self):
        tok = issue_token(self.SECRET, "duy", ttl_seconds=60, now=1000)
        self.assertIsNone(verify_token(self.SECRET, tok, now=1061))

    def test_wrong_secret(self):
        tok = issue_token(self.SECRET, "duy", ttl_seconds=60, now=1000)
        self.assertIsNone(verify_token("other", tok, now=1010))

    def test_tampered_payload(self):
        tok = issue_token(self.SECRET, "duy", ttl_seconds=60, now=1000)
        payload, sig = tok.split(".")
        other = issue_token(self.SECRET, "admin", ttl_seconds=60, now=1000).split(".")[0]
        self.assertIsNone(verify_token(self.SECRET, f"{other}.{sig}", now=1010))

    def test_garbage(self):
        self.assertIsNone(verify_token(self.SECRET, "", now=0))
        self.assertIsNone(verify_token(self.SECRET, "abc", now=0))
        self.assertIsNone(verify_token(self.SECRET, "a.b.c", now=0))

    def test_vietnamese_username(self):
        tok = issue_token(self.SECRET, "chị trang", ttl_seconds=60, now=1000)
        self.assertEqual(verify_token(self.SECRET, tok, now=1010), "chị trang")


class Exempt(unittest.TestCase):
    def test_login_exempt(self):
        self.assertTrue(is_exempt("POST", "/api/auth/login"))
        self.assertTrue(is_exempt("GET", "/api/auth/me"))

    def test_loopback_exempt(self):
        # bot role nội bộ gọi API qua localhost không token — không được 401
        self.assertTrue(is_exempt("POST", "/api/order/ban", "127.0.0.1"))
        self.assertTrue(is_exempt("POST", "/api/order/soan", "::1"))
        self.assertFalse(is_exempt("POST", "/api/order/ban", "100.64.1.5"))

    def test_tg_api_exempt(self):
        self.assertTrue(is_exempt("POST", "/api/tg/edit-message"))

    def test_pages_exempt(self):
        self.assertTrue(is_exempt("GET", "/orders"))
        self.assertTrue(is_exempt("GET", "/static/app.js"))
        self.assertTrue(is_exempt("GET", "/ws"))

    def test_options_exempt(self):
        self.assertTrue(is_exempt("OPTIONS", "/api/orders"))

    def test_api_gated(self):
        self.assertFalse(is_exempt("GET", "/api/orders"))
        self.assertFalse(is_exempt("POST", "/api/order/payment/tm"))
        self.assertFalse(is_exempt("POST", "/api/order/soan"))


class ExtractToken(unittest.TestCase):
    def test_bearer(self):
        self.assertEqual(extract_token({"Authorization": "Bearer abc"}, {}), "abc")

    def test_query_fallback(self):
        self.assertEqual(extract_token({}, {"token": "xyz"}), "xyz")

    def test_none(self):
        self.assertEqual(extract_token({}, {}), "")


class CorsAllowlist(unittest.TestCase):
    def test_webview_origin_allowed(self):
        from server_app.cors import cors_headers
        h = cors_headers("https://appassets.androidplatform.net")
        self.assertEqual(h.get("Access-Control-Allow-Origin"), "https://appassets.androidplatform.net")

    def test_unknown_origin_gets_nothing(self):
        from server_app.cors import cors_headers
        self.assertEqual(cors_headers("https://evil.example.com"), {})
        self.assertEqual(cors_headers(""), {})


class DigitUsernameRejected(unittest.TestCase):
    def test_all_digit_username_rejected(self):
        # username toàn số sẽ bị resolve_name nhầm là Telegram id
        import os
        import tempfile
        from user_store import add_user
        db = os.path.join(tempfile.mkdtemp(), "t.db")
        with self.assertRaises(ValueError):
            add_user("0912345678", "1234", db_path=db)
        add_user("duy91", "1234", db_path=db)  # có chữ cái — hợp lệ


if __name__ == "__main__":
    unittest.main()
