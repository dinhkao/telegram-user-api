"""Chuỗi nợ feed khách — logic THUẦN điền debt_after cho dãy sự kiện (unit-tested).

Tách từ server_app/customer_feed (chỉ nơi đó dùng). Mỗi event:
{kind, delta, stored (số KiotViet gốc hoặc None)} → mutate thêm debt_after + est.
Quy tắc nội suy neo mốc: xem docstring server_app/customer_feed.
"""
from __future__ import annotations

_TOL = 1.0   # sai số làm tròn cho phép khi đối chiếu 2 mốc
_ESCALATE_MAX = 12   # số bước nới đoạn lệch tối đa khi bắc cầu cục bộ thất bại


def _demote_misplaced_anchors(events: list[dict], current_debt) -> None:
    """Bỏ mốc gốc ĐẶT SAI CHỖ trên dòng thời gian (mutate events, stored → None).

    Kịch bản thật (Vinh Bảy Tình 2026-07-13): HĐ KiotViet của đơn được tạo SAU
    phiếu thu kế đó → khDebt snapshot chụp lúc nợ đã về 0 → mốc của đơn (khDebt +
    tổng) là số THẬT của KiotViet nhưng thuộc THỜI ĐIỂM KHÁC → rail nợ đọc sai
    (đơn 1.170k mà "nợ sau" không cộng đơn trước; thu tiền mà nợ không giảm).

    Chỉ demote khi CHỨNG MINH được: giữa 2 mốc 2 đầu đoạn lệch (GIỮ), nếu bỏ ít
    mốc chen giữa nhất mà mọi cặp mốc giữ lại CÂN (±_TOL) → các mốc bị bỏ là
    số-đúng-sai-chỗ, để nội suy điền lại (hiện ≈). Không bắc cầu được (chỉnh nợ
    tay KiotViet, thiếu sự kiện) → giữ nguyên mọi mốc như cũ, đoạn đó vẫn '—'.
    Đoạn lệch cục bộ không bắc được thì NỚI RỘNG dần 2 đầu (2 mốc rác cùng đợt
    nhập HĐ trễ TỰ CÂN với nhau → thành cặp 'tốt' giả che mất cầu — review
    2026-07-13). Ranh giới chấp nhận: chuỗi chỉnh-tay-KV triệt tiêu nhau đúng
    ±1đ vẫn có thể demote nhầm mốc thật (hiếm, số hiện ≈ để phân biệt).
    """
    for _ in range(len(events) or 1):
        if not _demote_pass(events, current_debt):
            return


def _demote_pass(events: list[dict], current_debt) -> bool:
    """1 lượt quét demote. True = có demote (mốc/cặp đổi → caller quét lại)."""
    n = len(events)
    # mốc = (index sự kiện, giá trị, là-phiếu-thu); mốc ảo cuối = nợ KV hiện tại
    anchors = [(i, float(e["stored"]), e.get("kind") == "payment")
               for i, e in enumerate(events) if e.get("stored") is not None]
    if current_debt is not None:
        anchors.append((n, float(current_debt), True))
    if len(anchors) < 3:
        return False

    # prefix delta: P[i] = Σ delta events[0..i-1] → Σ delta (a+1..b) = P[b+1] − P[a+1]
    prefix = [0.0]
    for e in events:
        prefix.append(prefix[-1] + float(e.get("delta") or 0.0))
    prefix.append(prefix[-1])   # index ảo n (delta 0)

    def _bal(a, b) -> bool:
        """Mốc a → mốc b có cân không (a[1] + Σ delta giữa == b[1])."""
        return abs(a[1] + (prefix[b[0] + 1] - prefix[a[0] + 1]) - b[1]) <= _TOL

    m = len(anchors)
    good = [_bal(anchors[k], anchors[k + 1]) for k in range(m - 1)]
    runs = []   # các đoạn lệch cực đại (lo, hi) theo index mốc
    k = 0
    while k < m - 1:
        if good[k]:
            k += 1
            continue
        j = k
        while j < m - 1 and not good[j]:
            j += 1
        runs.append((k, j))
        k = j
    # 1) bắc cầu cục bộ từng đoạn lệch
    for lo, hi in runs:
        if _demote_run(events, anchors, lo, hi, _bal):
            return True
    # 2) leo thang: nới đoạn nuốt dần mốc lân cận (kể cả cặp 'tốt' giả giữa
    #    2 mốc rác cùng đợt). Cap số bước — cụm HĐ nhập trễ 1 đợt chỉ vài mốc,
    #    còn đoạn không bao giờ bắc được (chỉnh tay KV) khỏi quét cả chuỗi.
    for lo, hi in runs:
        L, H, steps = lo, hi, 0
        while (L > 0 or H < m - 1) and steps < _ESCALATE_MAX:
            L, H, steps = max(0, L - 1), min(m - 1, H + 1), steps + 1
            if _demote_run(events, anchors, L, H, _bal):
                return True
    return False


def _demote_run(events: list[dict], anchors: list, lo: int, hi: int, bal) -> bool:
    """1 đoạn lệch anchors[lo..hi] (2 đầu GIỮ): tìm cách giữ NHIỀU mốc nhất
    (ưu tiên mốc phiếu thu — new_debt đo trực tiếp, mốc đơn chỉ là khDebt+tổng)
    sao cho mọi cặp liền kề cân; mốc rớt khỏi chuỗi → stored=None. Không có
    đường đi lo→hi thì bỏ qua (giữ nguyên). True = có demote."""
    if hi - lo < 2:
        return False   # không có mốc giữa để bỏ
    lo_ev, hi_ev = anchors[lo][0], anchors[hi][0]
    # chứng cứ yếu: sự kiện ts ĐOÁN trong đoạn (payment di sản neo cạnh đơn) —
    # vị trí delta không chắc → không demote mốc thật dựa trên nó
    if any(events[i].get("ts_guessed") for i in range(lo_ev, min(hi_ev + 1, len(events)))):
        return False
    best: dict[int, tuple] = {lo: (1, int(anchors[lo][2]), None)}   # (giữ, phiếu thu giữ, parent)
    for t in range(lo + 1, hi + 1):
        cand = None
        for s in range(lo, t):
            if s not in best or not bal(anchors[s], anchors[t]):
                continue
            sc = (best[s][0] + 1, best[s][1] + int(anchors[t][2]))
            if cand is None or sc > cand[:2]:
                cand = (sc[0], sc[1], s)
        if cand:
            best[t] = cand
    if hi not in best:
        return False   # không chứng minh được → giữ mọi mốc như cũ
    keep = []
    t = hi
    while t is not None:
        keep.append(t)
        t = best[t][2]
    keep.reverse()
    demoted = [t for t in range(lo + 1, hi) if t not in keep]
    if not demoted:
        return False
    # mô phỏng số sẽ nội suy trên đoạn: lòi nợ ÂM = cầu trùng hợp, không tin
    for s, t in zip(keep, keep[1:]):
        running = anchors[s][1]
        for i in range(anchors[s][0] + 1, anchors[t][0]):
            running += float(events[i].get("delta") or 0.0)
            if running < -_TOL:
                return False
    for t in demoted:
        events[anchors[t][0]]["stored"] = None
    return True


def _reorder_swapped_invoice_payment(events: list[dict]) -> None:
    """Hoán vị cặp ĐƠN-HĐ ↔ PHIẾU-THU bị đảo bởi timestamp (mutate tại chỗ).

    HĐ KiotViet của đơn nhiều khi được ĐẨY lên KV vài phút SAU khi tạo topic đơn,
    rơi ngay sau 1 phiếu thu mà KiotViet đã áp TRƯỚC → sort theo timestamp xếp
    [đơn, thu] trong khi nợ thật áp [thu, đơn]. Mốc nợ KiotViet (khDebt của đơn,
    new_debt của phiếu thu) mã hoá thứ tự áp dụng THẬT: nếu thứ tự hiện tại KHÔNG
    khớp chuỗi (mốc_trước + delta ≠ mốc) mà HOÁN VỊ lại khớp cả hai mốc (±_TOL) →
    đảo, để feed hiện đúng SỐ THẬT thay vì bị _demote_misplaced_anchors vứt mốc
    rồi nội suy sai (ca thật Loan Long Đại 2026-07-06). Chạy TRƯỚC demote.

    Bảo thủ — chỉ đảo khi CHỨNG MINH được: cặp kề [order (delta>0, stored), payment
    (delta<0, stored)], mốc lưu ngay trước (events[i-1].stored) làm đầu trái, không
    sự kiện nào ts_guessed (vị trí đoán không làm bằng chứng). Không thoả → để yên
    cho demote xử lý (mốc rác thật vẫn demote như cũ).
    """
    for i in range(1, len(events) - 1):
        prev, b, c = events[i - 1], events[i], events[i + 1]
        if b.get("kind") != "order" or c.get("kind") != "payment":
            continue
        if b.get("stored") is None or c.get("stored") is None or prev.get("stored") is None:
            continue
        if b.get("ts_guessed") or c.get("ts_guessed"):
            continue
        bd, cd = float(b.get("delta") or 0.0), float(c.get("delta") or 0.0)
        if not (bd > 0 and cd < 0):
            continue
        p, bs, cs = float(prev["stored"]), float(b["stored"]), float(c["stored"])
        cur_ok = abs(p + bd - bs) <= _TOL and abs(bs + cd - cs) <= _TOL
        swap_ok = abs(p + cd - cs) <= _TOL and abs(cs + bd - bs) <= _TOL
        if swap_ok and not cur_ok:
            events[i], events[i + 1] = c, b   # phiếu thu lên trước HĐ (thứ tự KV thật)


def _fill_debt_chain(events: list[dict], current_debt) -> None:
    """Điền debt_after cho MỌI sự kiện (events theo thời gian TĂNG dần, mutate).

    Mỗi event: {delta, stored (số gốc hoặc None)} → gắn thêm debt_after + est.
    Mốc = stored + mốc ảo cuối (current_debt). Tiến giữa các mốc, lùi trước mốc đầu.
    """
    n = len(events)

    # TIỀN XỬ LÝ — loạt phiếu thu dính nợ TRÙNG (bug resync: thu nhiều phiếu liền
    # tay → resync +6s của từng phiếu đều đọc ra cùng số nợ CUỐI từ KV → các phiếu
    # trước bị ghi trùng). Nợ sau 2 khoản thu >0 liên tiếp KHÔNG THỂ bằng nhau nếu
    # không có gì cộng nợ chen giữa → số của phiếu TRƯỚC là rác → bỏ (stored=None)
    # cho nội suy neo mốc điền lại (có kiểm chứng cân đoạn như thường).
    last_pay = None        # index phiếu thu gần nhất còn stored
    pos_delta_since = False   # có sự kiện cộng nợ chen giữa từ phiếu đó tới đây?
    for i, e in enumerate(events):
        if e.get("delta", 0) > 0:
            pos_delta_since = True
        if e.get("kind") != "payment" or e.get("stored") is None:
            continue
        if (last_pay is not None and not pos_delta_since and e.get("delta", 0) < 0
                and abs(float(events[last_pay]["stored"]) - float(e["stored"])) <= _TOL):
            events[last_pay]["stored"] = None
        last_pay = i
        pos_delta_since = False

    # TIỀN XỬ LÝ 1B — cặp ĐƠN-HĐ ↔ PHIẾU-THU bị đảo bởi timestamp (HĐ đẩy lên KV
    # sau, KiotViet áp phiếu thu trước) → hoán vị lại đúng thứ tự áp dụng KV để
    # khỏi bị demote vứt mốc thật. Chạy TRƯỚC demote.
    _reorder_swapped_invoice_payment(events)

    # TIỀN XỬ LÝ 2 — mốc đúng-số-nhưng-sai-chỗ (HĐ KiotViet tạo trễ) → demote
    _demote_misplaced_anchors(events, current_debt)

    for e in events:
        s = e.get("stored")
        e["debt_after"] = float(s) if s is not None else None
        e["est"] = s is None
    stored_idx = [i for i, e in enumerate(events) if not e["est"]]
    if not stored_idx and current_debt is None:
        return   # không có mốc nào — để None hết ('—')

    # GIỮA 2 mốc lưu: chỉ điền khi đoạn CÂN — mốc_trước + Σdelta == mốc_sau.
    # Không cân = có biến động ngoài app (chỉnh nợ tay KV, HĐ ngoài, xoá HĐ…)
    # → số nội suy trong đoạn đó KHÔNG tin được → giữ '—' (không hiện số sai).
    for a, b in zip(stored_idx, stored_idx[1:]):
        expected = events[a]["debt_after"] + sum(events[k]["delta"] for k in range(a + 1, b + 1))
        if abs(expected - events[b]["debt_after"]) <= _TOL:
            running = events[a]["debt_after"]
            for k in range(a + 1, b):
                running += events[k]["delta"]
                events[k]["debt_after"] = running
        # lệch → bỏ trống cả đoạn (est giữ None)

    # ĐUÔI (sau mốc lưu cuối): LÙI từ mốc ảo "hiện tại" (nợ KV đang có). Có mốc lưu
    # cuối để đối chiếu → cũng phải CÂN mới điền; không có mốc lưu nào → điền thẳng
    # nhưng bỏ nếu lòi số ÂM (nợ âm = chuỗi chắc chắn thiếu sự kiện).
    if current_debt is not None:
        last = stored_idx[-1] if stored_idx else -1
        vals: list[float] = []
        running = float(current_debt)
        for i in range(n - 1, last, -1):
            vals.append(running)
            running -= events[i]["delta"]
        ok = (abs(running - events[last]["debt_after"]) <= _TOL) if last >= 0 else all(v >= 0 for v in vals)
        if ok:
            for j, i in enumerate(range(n - 1, last, -1)):
                events[i]["debt_after"] = vals[j]

    # ĐẦU (trước mốc đầu): LÙI một phía, không có gì đối chiếu → chỉ điền khi
    # không lòi số âm.
    first = stored_idx[0] if stored_idx else n
    if first > 0 and first < n and events[first]["debt_after"] is not None:
        vals2: list[float] = []
        running = events[first]["debt_after"]
        for i in range(first - 1, -1, -1):
            running = running - events[i + 1]["delta"]
            vals2.append(running)
        if all(v >= 0 for v in vals2):
            for j, i in enumerate(range(first - 1, -1, -1)):
                if events[i]["debt_after"] is None:
                    events[i]["debt_after"] = vals2[j]
