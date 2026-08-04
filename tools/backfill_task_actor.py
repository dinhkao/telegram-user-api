"""CHẠY BÙ tên người thao tác cho các mốc task bị ghi `by=None` (token hết hạn).

Bối cảnh: token web sống 30 ngày; trước bản vá `stale_token_401`, token hết hạn chỉ
bị BỎ QUA im lặng (WEB_AUTH_ENABLED=false) → app vẫn chạy nhưng server không biết ai
đang bấm. Mọi mốc ghi `task_status.<bước>.by = None`, kéo theo: tiền giao hàng rơi vào
"Két chưa rõ" thay vì két người giao, việc nộp tiền không ai nhận, lịch sử ghi IP.

Bằng chứng để gán lại = audit_events: mỗi request có User-Agent; UA nào TRƯỚC ĐÓ từng
được nhận diện là đúng MỘT web_user thì các request vô danh cùng UA là của người đó
(1 máy = 1 người trong nhà; UA dùng chung >1 user bị BỎ QUA, không đoán).

MẶC ĐỊNH CHẠY THỬ (chỉ in ra, không ghi) — thêm --apply mới ghi vào DB.
Nối: audit (audit_events), order_store (blob đơn), task_store (mirror lại việc).

    .venv/bin/python tools/backfill_task_actor.py --from 2026-08-03
    .venv/bin/python tools/backfill_task_actor.py --from 2026-08-03 --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from order_store.schema import transaction  # noqa: E402
from order_store.serialization import _save_order, get_order_by_thread_id  # noqa: E402
from utils.db import get_connection  # noqa: E402

# alias type gửi từ client → khoá thật trong blob (giữ khớp server_app/order_api_tasks.py)
_ALIASES = {"soan": "soan_hang", "ban": "ban_hd", "giao": "giao_hang",
            "nop": "nop_tien", "nop-tien": "nop_tien"}
_MAX_SKEW = 180.0   # audit ghi lúc request XONG — mốc trong blob sớm hơn vài giây


def _ts(iso: str) -> float:
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _ua(payload: str) -> str:
    try:
        return str((json.loads(payload).get("headers") or {}).get("User-Agent") or "")
    except (json.JSONDecodeError, TypeError, AttributeError):
        return ""


def _body(payload: str) -> dict:
    """Body request đã ghi audit — audit lưu body dưới dạng CHUỖI JSON (không phải
    dict lồng), đọc thẳng .get('body') sẽ ra str → phải parse thêm một lớp."""
    try:
        b = json.loads(payload).get("body")
        if isinstance(b, str):
            b = json.loads(b)
    except (json.JSONDecodeError, TypeError):
        return {}
    return b if isinstance(b, dict) else {}


def ua_owners(conn, since: str) -> dict[str, str]:
    """{User-Agent: username} — chỉ giữ UA thuộc về ĐÚNG 1 web_user (không đoán bừa)."""
    seen: dict[str, set[str]] = defaultdict(set)
    for r in conn.execute(
            "SELECT actor_id, payload_json FROM audit_events"
            " WHERE actor_type = 'web_user' AND ts >= ?", (since,)):
        ua = _ua(r["payload_json"])
        if ua:
            seen[ua].add(str(r["actor_id"]))
    return {ua: next(iter(us)) for ua, us in seen.items() if len(us) == 1}


def anonymous_marks(conn, since: str) -> list[dict]:
    """Các lần bấm task KHÔNG có danh tính (actor_type='http_client') từ SINCE."""
    out: list[dict] = []
    for r in conn.execute(
            "SELECT ts, payload_json, result_json, source FROM audit_events"
            " WHERE actor_type = 'http_client' AND ts >= ?"
            "   AND source LIKE '%/api/order/task%' ORDER BY id", (since,)):
        try:
            status = int(json.loads(r["result_json"] or "{}").get("status") or 0)
        except (json.JSONDecodeError, TypeError, ValueError):
            status = 0
        if status != 200:
            continue
        body = _body(r["payload_json"])
        tid, raw_type = body.get("thread_id"), body.get("type")
        if not tid or not raw_type:
            continue
        out.append({"ts": _ts(r["ts"]), "at": r["ts"], "thread_id": int(tid),
                    "task": _ALIASES.get(str(raw_type), str(raw_type)),
                    "ua": _ua(r["payload_json"])})
    return out


def plan(conn, since: str) -> tuple[list[dict], list[dict]]:
    """(việc sẽ sửa, việc bỏ qua kèm lý do) — THUẦN ĐỌC, không ghi."""
    owners = ua_owners(conn, since)
    fixes: list[dict] = []
    skipped: list[dict] = []
    for m in anonymous_marks(conn, since):
        who = owners.get(m["ua"])
        if not who:
            skipped.append({**m, "why": "không suy được chủ máy từ User-Agent"})
            continue
        data = get_order_by_thread_id(conn, m["thread_id"])
        if data is None:
            skipped.append({**m, "why": "đơn không còn"})
            continue
        step = (data.get("task_status") or {}).get(m["task"])
        if not isinstance(step, dict):
            skipped.append({**m, "why": f"đơn không có mốc {m['task']}"})
            continue
        if step.get("by") not in (None, ""):
            skipped.append({**m, "why": f"đã có người: {step.get('by')}"})
            continue
        gap = abs(_ts(step.get("at")) - m["ts"])
        if gap > _MAX_SKEW:
            skipped.append({**m, "why": f"mốc lệch {gap:.0f}s — không chắc cùng lần bấm"})
            continue
        fixes.append({**m, "who": who, "name": data.get("khach_hang") or ""})
    return fixes, skipped


def apply(conn, fixes: list[dict]) -> int:
    """Ghi `by` vào blob đơn (RMW trong transaction như mọi mutation đơn)."""
    done = 0
    for f in fixes:
        with transaction(conn):
            data = get_order_by_thread_id(conn, f["thread_id"])
            if data is None:
                continue
            step = (data.get("task_status") or {}).get(f["task"])
            if not isinstance(step, dict) or step.get("by") not in (None, ""):
                continue   # đọc lại trong transaction — ai đó vừa sửa thì bỏ qua
            step["by"] = f["who"]
            _save_order(conn, f["thread_id"], data)
        done += 1
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="since", required=True, help="mốc ISO, vd 2026-08-03")
    ap.add_argument("--apply", action="store_true", help="ghi thật (mặc định chỉ in ra)")
    args = ap.parse_args()

    conn = get_connection()
    try:
        fixes, skipped = plan(conn, args.since)
        by_user: dict[str, int] = defaultdict(int)
        print(f"=== SẼ GÁN LẠI: {len(fixes)} mốc ===")
        for f in fixes:
            by_user[f["who"]] += 1
            print(f"  {f['at']}  đơn {f['thread_id']:>7}  {f['task']:<10} → {f['who']}")
        print("  tổng theo người:", dict(by_user) or "(không có)")
        print(f"\n=== BỎ QUA: {len(skipped)} ===")
        reasons: dict[str, int] = defaultdict(int)
        for s in skipped:
            reasons[s["why"].split(":")[0]] += 1
        for why, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>4}  {why}")
        if not args.apply:
            print("\n(CHẠY THỬ — thêm --apply để ghi)")
            return 0
        n = apply(conn, fixes)
        print(f"\nĐÃ GHI {n} mốc.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
