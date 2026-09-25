"""Hàng đợi push bền (server_app.push_outbox) + gửi thử lại (server_app.fcm.send_once)."""
import asyncio
import json
import sqlite3
import types

import pytest

from server_app import fcm, push_outbox
from server_app.push_outbox import MAX_ATTEMPTS, next_state

P = {"title": "💬 Bình luận mới", "body": "duy: hi", "data": {"thread_id": "1"}, "image_url": None,
     "tokens": None, "topic": True}


def test_all_delivered_is_sent():
    st, p, wait, _ = next_state(P, {"ok_users": ["duy"], "pending_tokens": [], "topic_pending": False}, 1)
    assert st == "sent" and wait is None and p["tokens"] == [] and p["topic"] is False


def test_network_error_before_any_device_resends_to_all():
    st, p, wait, s = next_state(P, {"pending_tokens": None, "topic_pending": True, "error": "No route to host"}, 1)
    assert st == "retry" and p["tokens"] is None and p["topic"] and wait == 30 and "No route" in s


def test_partial_only_missing_tokens_retried():
    st, p, _, _ = next_state(P, {"ok_users": ["duy"], "fail_users": ["tri"], "pending_tokens": ["tokTri"],
                                 "topic_pending": False}, 2)
    assert st == "retry" and p["tokens"] == ["tokTri"] and p["topic"] is False


def test_gives_up_after_max_attempts():
    st, _, wait, _ = next_state(P, {"pending_tokens": ["x"], "topic_pending": False}, MAX_ATTEMPTS)
    assert st == "failed" and wait is None


def test_disabled():
    assert next_state(P, {"disabled": True}, 1)[0] == "disabled"


# ── send_once với FCM giả: thử lại tức thì, chỉ gửi phần còn thiếu, dọn token chết ──
class _R:
    def __init__(self, ok, exc=None):
        self.success, self.exception = ok, exc


class Unregistered(Exception):
    pass


Unregistered.__name__ = "UnregisteredError"


def _fake_messaging(plan):
    """plan: list các lượt; mỗi lượt = Exception (lỗi cả lượt) | dict token→'ok'/'fail'/'dead'."""
    calls = []

    def send_each_for_multicast(msg, app=None):
        calls.append(list(msg.tokens))
        step = plan.pop(0)
        if isinstance(step, Exception):
            raise step
        rs = []
        for t in msg.tokens:
            v = step.get(t, "ok")
            rs.append(_R(v == "ok", None if v == "ok" else (Unregistered() if v == "dead" else RuntimeError("tạm"))))
        return types.SimpleNamespace(responses=rs)

    m = types.SimpleNamespace(
        AndroidConfig=lambda **k: None, AndroidNotification=lambda **k: None,
        Notification=lambda **k: None, MulticastMessage=lambda **k: types.SimpleNamespace(tokens=k["tokens"]),
        Message=lambda **k: None, send=lambda *a, **k: None, send_each_for_multicast=send_each_for_multicast)
    return m, calls


@pytest.fixture
def fake_fcm(monkeypatch):
    def setup(plan, rows=(("tA", "duy"), ("tB", "tri"))):
        m, calls = _fake_messaging(plan)
        import sys
        monkeypatch.setitem(sys.modules, "firebase_admin", types.SimpleNamespace(messaging=m))
        monkeypatch.setitem(sys.modules, "firebase_admin.messaging", m)
        monkeypatch.setattr("integrations.firebase_sync.core._get_app", lambda: object())
        monkeypatch.setattr(fcm, "FCM_ENABLED", True)
        monkeypatch.setattr(fcm, "FCM_TOPIC_FALLBACK", False)
        monkeypatch.setattr(fcm, "_INNER_WAITS", (0, 0))
        monkeypatch.setattr(fcm, "_eligible_rows", lambda audience=None: list(rows))
        dropped = []
        monkeypatch.setattr(fcm, "_drop_dead", lambda toks: dropped.extend(toks))
        return calls, dropped
    return setup


def test_send_once_retries_network_then_succeeds(fake_fcm):
    calls, _ = fake_fcm([ConnectionError("reset"), {}])
    r = fcm.send_once("t", "b")
    assert r["pending_tokens"] == [] and r["ok_users"] == ["duy", "tri"] and r["error"] is None
    assert len(calls) == 2


def test_send_once_retries_only_failed_token_and_drops_dead(fake_fcm):
    calls, dropped = fake_fcm([{"tB": "fail", "tA": "ok"}, {"tB": "ok"}], rows=(("tA", "duy"), ("tB", "tri"), ("tC", "x")))
    r = fcm.send_once("t", "b")
    assert calls[1] == ["tB"] and r["pending_tokens"] == []
    assert sorted(r["ok_users"]) == ["duy", "tri", "x"]


def test_send_once_returns_missing_after_inner_retries(fake_fcm):
    calls, _ = fake_fcm([{"tB": "fail"}, {"tB": "fail"}, {"tB": "fail"}])
    r = fcm.send_once("t", "b")
    assert r["pending_tokens"] == ["tB"] and r["fail_users"] == ["tri"] and len(calls) == 3


def test_dead_token_not_retried(fake_fcm):
    calls, dropped = fake_fcm([{"tB": "dead"}])
    r = fcm.send_once("t", "b")
    assert dropped == ["tB"] and r["pending_tokens"] == [] and len(calls) == 1


# ── deliver() qua DB thật (file tạm): lỗi → retry → vòng sau gửi bù đúng máy thiếu ──
def test_deliver_persists_and_resends_only_missing(monkeypatch, tmp_path):
    db = str(tmp_path / "n.db")
    from notif_store import add_notification, create_notif_table
    from notif_store.push_state import due_ids, mark_pending

    def conn():
        c = sqlite3.connect(db)
        c.row_factory = sqlite3.Row
        return c
    monkeypatch.setattr(push_outbox, "get_connection", conn)
    c = conn()
    create_notif_table(c)
    row = add_notification(c, type="comment", title="💬", body="x")
    assert "push_payload" not in row                     # token không lộ ra API
    mark_pending(c, row["id"], dict(P), 0)
    c.close()
    results = [{"ok_users": ["duy"], "fail_users": ["tri"], "pending_tokens": ["tB"], "topic_pending": False},
               {"ok_users": ["tri"], "pending_tokens": [], "topic_pending": False}]
    seen = []

    def fake_send(title, body, data, image_url, tokens, topic, audience=None):
        seen.append(tokens)
        return results.pop(0)
    monkeypatch.setattr(fcm, "send_once", fake_send)
    asyncio.run(push_outbox.deliver(row["id"]))
    c = conn()
    r = c.execute("SELECT push_state, push_attempts, push_payload FROM notifications").fetchone()
    assert r[0] == "retry" and r[1] == 1 and json.loads(r[2])["tokens"] == ["tB"]
    c.execute("UPDATE notifications SET push_next_at = 0")
    c.commit()
    assert due_ids(c, 10**10, "2000-01-01") == [row["id"]]
    c.close()
    asyncio.run(push_outbox.deliver(row["id"]))
    c = conn()
    assert c.execute("SELECT push_state, push_attempts FROM notifications").fetchone()[:] == ("sent", 2)
    assert seen == [None, ["tB"]]
