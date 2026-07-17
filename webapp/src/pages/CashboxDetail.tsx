// Timeline 1 KÉT TIỀN (#/ket/:key) — biến động vào/ra (mới nhất trước) với RAIL
// SỐ DƯ chạy theo (chấm trượt, cùng ngôn ngữ hình ảnh OrderTimeline) + danh sách
// đơn có tiền đang nằm trong két. Admin xoá được lần chuyển tay.
// Nối: api.getCashboxTimeline/cashboxTransferDelete, realtime, detail/OrderCards.
import { useEffect, useRef, useState } from "preact/hooks";
import { cashboxTransferDelete, cashboxWithdraw, currentUser, getCashboxTimeline, isOffice, soVN,
         type CashBox, type CashHolding, type CashMove } from "../api";
import { fmtDateTimeVN } from "../format";
import { onRealtime } from "../realtime";
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import { confirmDialog, toast } from "../ui/feedback";
import { EmptyState, ErrorState, Loading, LoadingInline } from "../ui/states";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { dayKeyOf, orderDayLabel } from "../detail/OrderCards";

const GROUP_SEC = 300;
const GAP_PXPS = 0.0333, GAP_MAX = 4000;
const MIN_JUNC = 34, SLIDE_M = 15;
const LAZY_INITIAL = 30, LAZY_BATCH = 30;
const hm = (v?: string) => (fmtDateTimeVN(v || "").match(/\d{2}:\d{2}/) || [""])[0];
function gapLabel(sec: number): string {
  const d = sec / 86400;
  if (d >= 60) return `${Math.round(d / 30)} tháng`;
  if (d >= 14) return `${Math.round(d / 7)} tuần`;
  if (d >= 1) return `${Math.round(d)} ngày`;
  const h = sec / 3600;
  if (h >= 1) return `${Math.round(h)} giờ`;
  return `${Math.max(1, Math.round(sec / 60))} phút`;
}

function MoveRow({ it, admin, onDeleteTransfer }: {
  it: CashMove; admin: boolean; onDeleteTransfer: (id: number) => void;
}) {
  return (
    <li class="pt-item">
      <div class="pt-line">
        <span class="pt-time">{hm(it.at)}</span>
        <span class={"pt-tag " + it.dir}>{it.dir === "in" ? "+" : "−"}</span>
        <span class="pt-line-txt">
          {it.actor ? <><b class="pt-who">{it.actor}</b> </> : null}
          <b>{it.label}</b> <b class={it.dir === "in" ? "cash-in" : "cash-out"}>
            {it.dir === "in" ? "+" : "−"}{soVN(it.amount)}đ</b>
          {" — "}
          {it.dir === "in" ? "từ " : "sang "}
          {it.other_key.startsWith("user:") || it.other_key.startsWith("tg:") || it.other_key === "office"
            || it.other_key === "bank" || it.other_key === "debt" || it.other_key === "unknown"
            ? <a class="pt-inl" href={`#/ket/${encodeURIComponent(it.other_key)}`}>{it.other_name}</a>
            : <span>{it.other_name}</span>}
          {it.thread_id ? (
            <> · <a class="pt-inl" href={`#/order/${it.thread_id}`}>{it.order_name || `đơn #${it.thread_id}`}</a></>
          ) : null}
          {it.purchase_id ? (
            <> · <a class="pt-inl" href={`#/nhap-hang/${it.purchase_id}`}>phiếu nhập #{it.purchase_id}</a></>
          ) : null}
          {it.note ? <> · <span class="muted">{it.note}</span></> : null}
          {it.transfer_id && admin ? (
            <> · <button class="link-btn cash-del" onClick={() => onDeleteTransfer(it.transfer_id!)}>xoá</button></>
          ) : null}
        </span>
      </div>
      <span class="pt-rail" />
    </li>
  );
}

function Junction({ height, label, amount }: { height: number; label: string | null; amount?: number | null }) {
  return (
    <li class="pt-junc" style={height ? { height: `${height}px` } : undefined}>
      <span class="pt-junc-mid">
        {label && <span class="pt-gaplbl pt-slide"><span class="fg-label">· {label} ·</span></span>}
      </span>
      <span class="pt-rail">
        <span class="pt-bead pt-slide">
          {amount != null && <span class="pt-dot-amt">{soVN(amount)}</span>}
          <span class="pt-dot pt-dot-static" />
        </span>
      </span>
    </li>
  );
}

function WithdrawModal({ boxKey, balance, onDone, onClose }: {
  boxKey: string; balance: number; onDone: () => void; onClose: () => void;
}) {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useScrollLock(true);
  usePopupBack(true, onClose);
  const amt = parseInt(amount.replace(/[^\d]/g, ""), 10) || 0;
  const submit = async () => {
    if (amt <= 0) return toast("Nhập số tiền", "info");
    if (amt > balance) return toast("Số tiền vượt quá số dư két", "info");
    setBusy(true);
    try {
      await cashboxWithdraw(boxKey, amt, note.trim());
      toast("Đã thu hồi tiền", "ok");
      onDone();
    } catch (e: any) {
      toast(e?.message || "Thu hồi thất bại", "err");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="modal-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head"><Icon name="wallet" size={16} /> Thu hồi tiền khỏi két</div>
        <div class="muted small">
          Số dư hiện tại: <b>{soVN(balance)}đ</b>
          {" · "}
          <button class="link-btn" onClick={() => setAmount(String(balance))}>rút hết</button>
        </div>
        <input class="quy-input" type="text" inputMode="numeric" placeholder="Số tiền"
          value={amount} onInput={(e: any) => setAmount(e.currentTarget.value)} />
        <input class="quy-input" placeholder="Ghi chú (vd rút tiền mặt)"
          value={note} onInput={(e: any) => setNote(e.currentTarget.value)} />
        <div class="muted small">Tiền sẽ ra khỏi hệ két — admin hoàn tác được ở timeline.</div>
        <div class="row">
          <button class="btn" onClick={onClose} disabled={busy}>Huỷ</button>
          <button class="btn danger" onClick={submit} disabled={busy}>
            {busy ? "Đang xử lý…" : amt > 0 ? `Thu hồi ${soVN(amt)}đ` : "Thu hồi"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function CashboxDetail({ boxKey }: { boxKey: string }) {
  const [box, setBox] = useState<CashBox | null>(null);
  const [items, setItems] = useState<CashMove[]>([]);
  const [holdings, setHoldings] = useState<CashHolding[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const listRef = useRef<HTMLUListElement>(null);
  const [shown, setShown] = useState(LAZY_INITIAL);
  const moreRef = useRef<HTMLLIElement>(null);
  const admin = currentUser()?.role === "admin";

  const load = () => {
    getCashboxTimeline(boxKey)
      .then((r) => {
        setBox(r.box); setItems(r.items); setHoldings(r.holdings); setTruncated(r.truncated); setErr("");
      })
      .catch((e: any) => setErr(e?.message || "Lỗi tải két"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { setLoading(true); load(); }, [boxKey]);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "order_changed" || e.type === "orders_changed"
        || e.type === "cashbox_changed" || e.type === "resync") {
        clearTimeout(t); t = setTimeout(load, 600);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, [boxKey]);

  useEffect(() => { setShown(LAZY_INITIAL); }, [items]);
  useEffect(() => {
    const el = moreRef.current;
    if (!el || shown >= items.length) return;
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) setShown((s) => Math.min(items.length, s + LAZY_BATCH));
    }, { rootMargin: "800px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [shown, items]);

  // chấm số dư trượt theo cuộn (same cơ chế OrderTimeline/BoxTimeline)
  useEffect(() => {
    const apply = () => {
      const juncs = listRef.current?.querySelectorAll<HTMLElement>(".pt-junc");
      if (!juncs) return;
      const pin = window.innerHeight * 0.45;
      juncs.forEach((j) => {
        const r = j.getBoundingClientRect();
        const off = r.height <= SLIDE_M * 2 ? r.height / 2 : Math.min(Math.max(pin - r.top, SLIDE_M), r.height - SLIDE_M);
        j.querySelectorAll<HTMLElement>(".pt-slide").forEach((el) => { el.style.top = `${off}px`; });
      });
    };
    let raf = 0, running = false, lastY = -1, idle = 0;
    const tick = () => {
      const y = window.scrollY;
      if (y !== lastY) { lastY = y; idle = 0; apply(); }
      else if (++idle > 20) { running = false; return; }
      raf = requestAnimationFrame(tick);
    };
    const onScroll = () => { if (!running) { running = true; idle = 0; raf = requestAnimationFrame(tick); } };
    window.addEventListener("scroll", onScroll, { passive: true });
    const t = setTimeout(apply, 60);
    return () => { window.removeEventListener("scroll", onScroll); cancelAnimationFrame(raf); clearTimeout(t); };
  }, [items, shown]);

  const delTransfer = async (id: number) => {
    if (!(await confirmDialog("Xoá lần chuyển tiền này? Số dư 2 két sẽ tính lại.", { danger: true }))) return;
    try {
      await cashboxTransferDelete(id);
      toast("Đã xoá lần chuyển", "ok");
      load();
    } catch (e: any) {
      toast(e?.message || "Xoá thất bại", "err");
    }
  };

  const [showWithdraw, setShowWithdraw] = useState(false);
  const office = isOffice();
  const isMyBox = boxKey === `user:${currentUser()?.username || ""}`;
  const canWithdraw = office && (isMyBox || admin);

  if (loading && !box) return <Loading />;
  if (err || !box) return <ErrorState msg={err || "Không tìm thấy"} onRetry={load} />;

  const rows: any[] = [];
  if (items.length) {
    rows.push(<li key="d-top" class="pt-day"><div class="order-day-head">{orderDayLabel(dayKeyOf(items[0].at))}</div></li>);
    rows.push(<Junction key="j-top" height={MIN_JUNC} label={null} amount={box.balance} />);
  }
  const lim = Math.min(shown, items.length);
  for (let i = 0; i < lim; i++) {
    const it = items[i];
    rows.push(<MoveRow key={`e-${i}`} it={it} admin={admin} onDeleteTransfer={delTransfer} />);
    const older = items[i + 1];
    if (older && i + 1 < lim) {
      const dsec = Math.max(0, it.ts - older.ts);
      const cross = dayKeyOf(it.at) !== dayKeyOf(older.at);
      if (dsec > GROUP_SEC) {
        const gh = Math.max(MIN_JUNC, cross ? 0 : Math.round(Math.min(dsec * GAP_PXPS, GAP_MAX)));
        rows.push(<Junction key={`j-${i}`} height={gh} label={cross ? null : gapLabel(dsec)} amount={older.after} />);
      }
      if (cross) rows.push(<li key={`d-${i}`} class="pt-day"><div class="order-day-head">{orderDayLabel(dayKeyOf(older.at))}</div></li>);
    }
  }
  if (lim < items.length) rows.push(<li key="more" ref={moreRef} class="pt-more"><span class="muted small"><LoadingInline label="Đang tải thêm…" /></span></li>);

  return (
    <div class="place-tl">
      <div class="prod-detail-head">
        <BackLink fallback="#/ket" />
        <div>
          <div class="prod-sp big"><Icon name="wallet" size={17} /> {box.name}</div>
          <div class="prod-date muted">Timeline két tiền</div>
        </div>
      </div>

      <div class="pt-head card">
        <div>
          <div class={"pt-total-big" + (box.balance ? "" : " zero")}>{soVN(box.balance)}đ</div>
          <div class="muted small">
            số dư hiện tại
            {box.in_today > 0 && <> · hôm nay <b class="cash-in">+{soVN(box.in_today)}</b></>}
            {box.out_today > 0 && <> / <b class="cash-out">−{soVN(box.out_today)}</b></>}
          </div>
        </div>
        <div class="pt-head-right">
          {canWithdraw && (
            <button class="btn small" onClick={() => setShowWithdraw(true)}>
              <Icon name="wallet" size={14} /> Thu hồi
            </button>
          )}
          <span class="muted small">{items.length} biến động{truncated ? " (mới nhất)" : ""}</span>
        </div>
      </div>

      {showWithdraw && (
        <WithdrawModal boxKey={boxKey} balance={box.balance} onDone={() => { setShowWithdraw(false); load(); }} onClose={() => setShowWithdraw(false)} />
      )}

      {holdings.length > 0 && (
        <div class="cash-holdings card">
          <div class="cash-sect muted small">TIỀN CỦA {holdings.length} ĐƠN ĐANG NẰM Ở ĐÂY</div>
          {holdings.map((h) => (
            <a key={h.thread_id} class="cash-hold-row" href={`#/order/${h.thread_id}`}>
              <span class="cash-hold-name">
                {h.name}
                {h.note === "chieu_lay_tien" && <span class="cash-badge">🟨 chiều lấy tiền</span>}
                {h.overdue && <span class="cash-badge">⏰ quá hạn nộp</span>}
              </span>
              <span class="cash-hold-amt">{soVN(h.amount)}đ</span>
              <span class="muted small">{fmtDateTimeVN(h.since_at)}</span>
            </a>
          ))}
        </div>
      )}

      {items.length === 0 ? (
        <EmptyState>Két này chưa có biến động nào.</EmptyState>
      ) : (
        <ul class="pt-list" ref={listRef}>{rows}</ul>
      )}
      {truncated && <div class="muted small pt-trunc">Chỉ hiện {items.length} biến động gần nhất.</div>}
    </div>
  );
}
