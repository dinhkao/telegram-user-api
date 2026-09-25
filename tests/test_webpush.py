"""Web Push (server_app.webpush): gửi THẬT qua pywebpush tới 1 'dịch vụ push' giả tại máy,
rồi giải mã bằng khoá phía điện thoại → chứng minh mã hoá aes128gcm + VAPID đúng chuẩn.
Kèm: chặn endpoint lạ (SSRF), phân loại lỗi (404/410 = xoá đăng ký, 403 = giữ), URL mở."""
import base64
import http.server
import json
import os
import threading

import http_ece
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from server_app import webpush


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


@pytest.fixture
def vapid(tmp_path, monkeypatch):
    key = ec.generate_private_key(ec.SECP256R1())
    p = tmp_path / "vapid.pem"
    p.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()))
    monkeypatch.setattr(webpush, "VAPID_PRIVATE_KEY_FILE", str(p))
    webpush._vapid.cache_clear()
    yield
    webpush._vapid.cache_clear()


def _fake_push_service(status: int):
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            got["headers"] = self.headers   # tra không phân biệt hoa/thường
            got["body"] = self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(status)
            self.end_headers()

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    return srv, got


def _phone():
    priv = ec.generate_private_key(ec.SECP256R1())
    pub = priv.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    auth = os.urandom(16)
    return priv, pub, auth


def test_push_is_encrypted_and_decryptable_by_phone(vapid):
    srv, got = _fake_push_service(201)
    priv, pub, auth = _phone()
    sub = {"endpoint": f"http://127.0.0.1:{srv.server_port}/push", "username": "trinh",
           "p256dh": _b64(pub), "auth": _b64(auth)}
    payload = json.dumps({"title": "💰 Duy nhận 1.500.000đ", "body": "Mỹ st", "url": "/app/#/order/5"})
    assert webpush._push_one(sub, payload) == "ok"
    srv.server_close()
    assert got["headers"]["Content-Encoding"] == "aes128gcm"
    assert got["headers"]["Authorization"].startswith("vapid t=")
    assert got["headers"]["Urgency"] == "high"
    plain = http_ece.decrypt(got["body"], private_key=priv, auth_secret=auth, version="aes128gcm")
    assert json.loads(plain)["title"] == "💰 Duy nhận 1.500.000đ"


@pytest.mark.parametrize("status,expect", [(410, "dead"), (404, "dead"), (403, "fail"), (429, "fail"), (500, "fail")])
def test_status_classification(vapid, status, expect):
    srv, _ = _fake_push_service(status)
    _, pub, auth = _phone()
    sub = {"endpoint": f"http://127.0.0.1:{srv.server_port}/p", "username": "x", "p256dh": _b64(pub), "auth": _b64(auth)}
    assert webpush._push_one(sub, "{}") == expect
    srv.server_close()


def test_public_key_is_65_byte_point(vapid):
    raw = base64.urlsafe_b64decode(webpush.public_key() + "==")
    assert len(raw) == 65 and raw[0] == 4


def test_only_real_push_services_allowed():
    ok = webpush.endpoint_allowed
    assert ok("https://web.push.apple.com/QK7x")
    assert ok("https://fcm.googleapis.com/fcm/send/abc")
    assert not ok("http://web.push.apple.com/x")
    assert not ok("https://127.0.0.1/x") and not ok("https://evil.com/web.push.apple.com")


def test_click_url():
    assert webpush.target_url({"route": "#/thung/5"}) == "/app/#/thung/5"
    assert webpush.target_url({"thread_id": "9", "type": "comment", "comment_id": "3"}) == "/app/#/order/9?focus=comment:3"
    assert webpush.target_url({}) == "/app/"


def test_subscribers_filtered_like_fcm():
    import sqlite3
    from notif_store.webpush_subs import eligible_subs, register_sub
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE web_users (username TEXT, role TEXT, disabled INTEGER)")
    c.executemany("INSERT INTO web_users VALUES (?,?,?)",
                  [("trinh", "staff", 0), ("duy", "admin", 0), ("hien", "chat_luong", 0), ("old", "staff", 1)])
    for u in ("trinh", "duy", "hien", "old"):
        register_sub(c, endpoint=f"https://web.push.apple.com/{u}", username=u, p256dh="k", auth="a")
    register_sub(c, endpoint="https://web.push.apple.com/trinh", username="trinh", p256dh="k2", auth="a")  # ghi đè
    assert sorted(s["username"] for s in eligible_subs(c)) == ["duy", "trinh"]
    assert [s["username"] for s in eligible_subs(c, only_roles=("admin", "van_phong"))] == ["duy"]
