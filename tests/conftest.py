"""Cấu hình chung cho mọi test.

⚠ CHẶN PUSH/THÔNG BÁO THẬT: nhiều route test gọi handler thật (bình luận, thu tiền…)
mà handler đó bắn push qua server_app.notify.push_bg — hàm này ghi vào app.db THẬT
(bảng notifications) + gửi FCM THẬT tới điện thoại. Đã xảy ra 25/09/2026: test
worker_moc bắn 16 push "Trao đổi · Mốc lương" giả tới máy văn phòng. Fixture autouse
dưới đây vô hiệu hoá cả 2 đường cho MỌI test; server_app.notify.push_bg còn tự chặn khi
thấy biến PYTEST_CURRENT_TEST (lớp an toàn thứ 2). Test cần kiểm push thì gọi thẳng
push_outbox/fcm với FCM giả (xem tests/test_push_outbox.py).
"""
import pytest


@pytest.fixture(autouse=True)
def _no_real_push(monkeypatch):
    import server_app.fcm as fcm
    import server_app.notify as notify
    sent: list = []
    monkeypatch.setattr(notify, "push_bg", lambda *a, **k: sent.append((a, k)))
    monkeypatch.setattr(fcm, "FCM_ENABLED", False)
    yield sent
