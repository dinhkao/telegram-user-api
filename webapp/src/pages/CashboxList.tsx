// Trang KÉT TIỀN (#/ket) — "ai đang giữ tiền": mỗi người 1 két + két văn phòng /
// ngân hàng / khách nợ / chưa rõ. Số dư derive từ blob đơn (server), realtime theo
// order_changed/cashbox_changed. Văn phòng: nút chuyển tiền tay giữa két.
// Nối: api.getCashboxes/cashboxTransfer, ui/SelectPopup, ui/feedback, ui/states.
import { useEffect, useState } from "preact/hooks";
import { getCashboxes, cashboxTransfer, isOffice, soVN, type CashBox } from "../api";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { SelectPopup } from "../ui/SelectPopup";
import { toast } from "../ui/feedback";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";
import { EmptyState, ErrorState, SkeletonList } from "../ui/states";
import { PageHead } from "../ui/PageHead";

let boxCache: { boxes: CashBox[]; since: string; totalUnpaid?: number } | null = null;
onRealtime((e) => {
  if (e.type === "order_changed" || e.type === "orders_changed"
    || e.type === "cashbox_changed" || e.type === "resync") boxCache = null;
});

const BOX_ICON: Record<string, string> = {
  office: "banknote", bank: "bank", debt: "clipboard", unknown: "search",
};

function BoxCard({ b }: { b: CashBox }) {
  const icon = BOX_ICON[b.key] || "user";
  const zero = b.balance === 0 && b.holding_count === 0;
  return (
    <a class={"cash-box" + (zero ? " cash-zero" : "")} href={`#/ket/${encodeURIComponent(b.key)}`}>
      <div class="cash-box-head">
        <span class="cash-box-name"><Icon name={icon} size={15} /> {b.name}</span>
        {b.overdue_count > 0 && <span class="cash-badge">⏰ {b.overdue_count} đơn quá hạn nộp</span>}
      </div>
      <div class={"cash-box-bal" + (b.balance ? "" : " zero")}>{soVN(b.balance)}đ</div>
      <div class="muted small">
        {b.holding_count > 0 ? <>tiền của {b.holding_count} đơn chưa thu xong</> : <>không giữ tiền đơn nào</>}
        {(b.in_today > 0 || b.out_today > 0) && (
          <> · hôm nay {b.in_today > 0 && <b class="cash-in">+{soVN(b.in_today)}</b>}
            {b.in_today > 0 && b.out_today > 0 && " / "}
            {b.out_today > 0 && <b class="cash-out">−{soVN(b.out_today)}</b>}</>
        )}
      </div>
    </a>
  );
}

function TransferModal({ boxes, onDone, onClose }: { boxes: CashBox[]; onDone: () => void; onClose: () => void }) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useScrollLock(true);
  usePopupBack(true, onClose);
  const opts = boxes.map((b) => ({ value: b.key, label: b.name, sub: `${soVN(b.balance)}đ` }));
  const amt = parseInt(amount.replace(/[^\d]/g, ""), 10) || 0;
  const submit = async () => {
    if (!from || !to || from === to) return toast("Chọn két nguồn và két đích khác nhau", "info");
    if (amt <= 0) return toast("Nhập số tiền", "info");
    setBusy(true);
    try {
      await cashboxTransfer(from, to, amt, note.trim());
      toast("Đã chuyển tiền két", "ok");
      onDone();
    } catch (e: any) {
      toast(e?.message || "Chuyển thất bại", "err");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="modal-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head"><Icon name="wallet" size={16} /> Chuyển tiền giữa két</div>
        <SelectPopup value={from} options={opts} onChange={setFrom} title="Từ két" placeholder="Từ két…" searchable />
        <SelectPopup value={to} options={opts} onChange={setTo} title="Đến két" placeholder="Đến két…" searchable />
        <input class="quy-input" type="text" inputMode="numeric" placeholder="Số tiền (vd 500000)"
          value={amount} onInput={(e: any) => setAmount(e.currentTarget.value)} />
        <input class="quy-input" placeholder="Ghi chú (vd kết sổ cuối ngày)"
          value={note} onInput={(e: any) => setNote(e.currentTarget.value)} />
        {amt > 0 && <div class="muted small">Sẽ chuyển <b>{soVN(amt)}đ</b></div>}
        <div class="row">
          <button class="btn" onClick={onClose} disabled={busy}>Huỷ</button>
          <button class="btn primary" onClick={submit} disabled={busy}>{busy ? "Đang chuyển…" : "Chuyển"}</button>
        </div>
      </div>
    </div>
  );
}

export function CashboxList() {
  const [boxes, setBoxes] = useState<CashBox[]>(boxCache?.boxes || []);
  const [totalUnpaid, setTotalUnpaid] = useState<number | undefined>(boxCache?.totalUnpaid);
  const [since, setSince] = useState(boxCache?.since || "");
  const [loading, setLoading] = useState(!boxCache);
  const [err, setErr] = useState("");
  const [showTransfer, setShowTransfer] = useState(false);
  const office = isOffice();

  const load = () => {
    getCashboxes()
      .then((d) => {
        setBoxes(d.boxes); setTotalUnpaid(d.total_unpaid); setSince(d.since); setErr("");
        boxCache = { boxes: d.boxes, since: d.since, totalUnpaid: d.total_unpaid };
      })
      .catch((e: any) => setErr(e?.message || "Lỗi tải két tiền"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { if (!boxCache) load(); }, []);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "order_changed" || e.type === "orders_changed"
        || e.type === "cashbox_changed" || e.type === "resync") {
        clearTimeout(t); t = setTimeout(load, 600);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, []);

  if (loading && !boxes.length) return <SkeletonList rows={5} />;
  const special = boxes.filter((b) => b.kind === "special");
  const people = boxes.filter((b) => b.kind !== "special");
  const holdingPeople = people.filter((b) => b.balance !== 0 || b.holding_count > 0);
  const idlePeople = people.filter((b) => b.balance === 0 && b.holding_count === 0);

  return (
    <div class="cash-page">
      <PageHead fallback="#/home"
        title={<><Icon name="wallet" size={18} /> Két tiền</>}
        sub={typeof totalUnpaid === "number" ? `Khách còn nợ (đơn từ ${since})` : "Két tiền của bạn"}
        right={
          <div class="cash-head-btns">
            <a class="btn small" href="#/huong-dan/ket-tien" title="Hướng dẫn két tiền">
              <Icon name="info" size={14} />
            </a>
            {office && (
              <button class="btn" onClick={() => setShowTransfer(true)}>
                <Icon name="refresh" size={14} /> Chuyển tiền
              </button>
            )}
          </div>
        } />
      {typeof totalUnpaid === "number" && <div class="pt-total-big">{soVN(totalUnpaid)}đ</div>}

      {!boxes.length && (err
        ? <ErrorState msg={err} onRetry={() => { setLoading(true); load(); }} />
        : <EmptyState>Chưa có biến động tiền nào.</EmptyState>)}

      {holdingPeople.length > 0 && <div class="ie-head">Người đang giữ tiền</div>}
      {holdingPeople.map((b) => <BoxCard key={b.key} b={b} />)}
      {special.length > 0 && <div class="ie-head">Két chung</div>}
      {special.map((b) => <BoxCard key={b.key} b={b} />)}
      {idlePeople.length > 0 && <div class="ie-head">Không giữ tiền</div>}
      {idlePeople.map((b) => <BoxCard key={b.key} b={b} />)}

      {showTransfer && (
        <TransferModal boxes={boxes} onClose={() => setShowTransfer(false)}
          onDone={() => { setShowTransfer(false); boxCache = null; load(); }} />
      )}
    </div>
  );
}
