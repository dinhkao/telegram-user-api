"""Luật thuần chấm công: validate batch từ collector + so bearer token. Không IO.

Dùng bởi attendance_store.store + server_app/attendance_routes. Unit-test:
tests/test_attendance_store.py.
"""
from __future__ import annotations

import hmac
import re
from datetime import datetime, timedelta, timezone

MAX_EVENTS_PER_BATCH = 5000

_EVENT_ID = re.compile(r"^[0-9a-f]{64}$")
# Máy chấm công chỉ có dữ liệu từ 2020s; chặn timestamp rác (năm 1970/3000…)
_MIN_TS = datetime(2020, 1, 1, tzinfo=timezone.utc)


def token_ok(expected: str, presented: str) -> bool:
    """So bearer token constant-time. Token server CHƯA cấu hình → luôn fail (đóng)."""
    if not expected or not presented:
        return False
    return hmac.compare_digest(expected.encode(), presented.encode())


def _parse_ts(value, *, aware_required: bool) -> datetime | None:
    """ISO-8601 → datetime; None nếu hỏng. aware_required → bắt buộc có offset."""
    if not isinstance(value, str) or not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if aware_required and ts.tzinfo is None:
        return None
    return ts


def validate_event(ev, allowed_machines: set[str], now: datetime) -> str | None:
    """Chuỗi lỗi (tiếng Anh — trả cho collector) hoặc None nếu event hợp lệ.

    Mutates ev: chuẩn hoá occurred_ymd (ngày theo offset của punch — máy ở +07:00).
    """
    if not isinstance(ev, dict):
        return "event must be an object"
    eid = ev.get("event_id")
    if not isinstance(eid, str) or not _EVENT_ID.match(eid):
        return "event_id must be a 64-char hex sha256"
    if ev.get("machine_id") not in allowed_machines:
        return f"unknown machine_id in event {eid[:8]}"
    code = ev.get("employee_code")
    if not isinstance(code, str) or not code.strip():
        return f"employee_code missing in event {eid[:8]}"
    ts = _parse_ts(ev.get("occurred_at"), aware_required=True)
    if ts is None:
        return f"occurred_at must be timezone-aware ISO-8601 in event {eid[:8]}"
    if not (_MIN_TS <= ts <= now):
        return f"occurred_at out of range in event {eid[:8]}"
    for field in ("verify_mode", "in_out_mode", "work_code", "source_index"):
        if not isinstance(ev.get(field, 0), int):
            return f"{field} must be an integer in event {eid[:8]}"
    if ev.get("collected_at") is not None and _parse_ts(ev.get("collected_at"), aware_required=False) is None:
        return f"collected_at invalid in event {eid[:8]}"
    ev["occurred_ymd"] = ts.strftime("%Y-%m-%d")
    return None


def validate_batch(payload, allowed_machines: set[str], now: datetime | None = None):
    """(events, error). error != None → 400/422; events đã gắn occurred_ymd."""
    if now is None:
        now = datetime.now(timezone.utc)
    now = now + timedelta(days=1)   # chấp nhận đồng hồ collector chạy nhanh nhẹ
    if not isinstance(payload, dict):
        return None, "body must be a JSON object"
    if payload.get("schema_version") != 1:
        return None, "unsupported schema_version"
    if payload.get("machine_id") not in allowed_machines:
        return None, "unknown machine_id"
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        return None, "events must be a non-empty list"
    if len(events) > MAX_EVENTS_PER_BATCH:
        return None, f"too many events (max {MAX_EVENTS_PER_BATCH})"
    seen: set[str] = set()
    for ev in events:
        err = validate_event(ev, allowed_machines, now)
        if err:
            return None, err
        if ev["event_id"] in seen:
            # trùng TRONG 1 batch: collector không bao giờ tạo — coi là payload hỏng
            return None, f"duplicate event_id inside batch {ev['event_id'][:8]}"
        seen.add(ev["event_id"])
    return events, None


# ── Quy giờ chấm → CÔNG + TĂNG CA (thuần, cùng luật với lưới webapp) ─────────
# 2 ca: sáng 7–11, chiều 13–17 (ngày đủ = 480ph = 1 công). Cặp chấm liên tiếp
# (vào→ra) = khoảng có mặt; lần chấm LẺ cuối bỏ (thiếu vào/ra — không đoán).
# Tăng ca = có mặt SAU giờ hết ca (11h/17h) khi chấm ra TRỄ HƠN 15ph (grace);
# trước 7h KHÔNG tính (đến sớm không phải tăng ca); khoảng vào-ra xuyên TRỌN giờ
# trưa (≤11h → ≥13h, không chấm giữa) coi là quên chấm trưa → 11–13h không tính TC.
SHIFT_WINDOWS = ((7 * 60, 11 * 60), (13 * 60, 17 * 60))
FULL_DAY_MIN = 480          # 2 ca × 4 giờ
OT_GRACE_MIN = 15
OT_END_OF_DAY = 24 * 60


def _mins(t: str) -> int:
    return int(t[:2]) * 60 + int(t[3:5])


def work_stats(times: list[str]) -> tuple[int, int]:
    """['HH:MM' tăng dần] 1 ngày → (phút CÔNG trong 2 ca, phút TĂNG CA)."""
    ts = sorted(_mins(t) for t in times)
    spans = [(ts[i], ts[i + 1]) for i in range(0, len(ts) - 1, 2) if ts[i + 1] > ts[i]]
    work = ot = 0
    for s, e in spans:
        for a, b in SHIFT_WINDOWS:
            work += max(0, min(e, b) - max(s, a))
        morning_end, afternoon_start = SHIFT_WINDOWS[0][1], SHIFT_WINDOWS[1][0]
        crosses_lunch = s <= morning_end and e >= afternoon_start
        # tăng ca sau 11h (làm lấn giờ trưa) — trừ ca xuyên trưa (nghi quên chấm)
        if not crosses_lunch and s <= morning_end < e:
            seg = min(e, afternoon_start) - morning_end
            if seg > OT_GRACE_MIN:
                ot += seg
        # tăng ca sau 17h
        if e > SHIFT_WINDOWS[1][1] + OT_GRACE_MIN:
            ot += min(e, OT_END_OF_DAY) - SHIFT_WINDOWS[1][1]
    return work, ot
