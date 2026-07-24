// NHẬP PHỤ CẤP (#/nhap-phu-cap) — CHỈ văn phòng. Ghi phụ cấp cho thợ theo tháng.
// Không xoá — VÔ HIỆU kèm lý do, dòng vẫn hiện (gạch ngang, ai/lúc nào/lý do).
import { useEffect, useState } from "preact/hooks";
import {
  addPayrollAllowance, isOffice, listAllAllowances, listPayrollAllowances, listWorkers, soVN, voidPayrollAllowance,
  type SalaryAllowance, type Worker,
} from "../api";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { SelectPopup } from "../ui/SelectPopup";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { toast, promptDialog } from "../ui/feedback";

import { moneyR as money, pad2 as pad, curYM, shiftYM, ymLabel, isoDate } from "../format";
const num = (s: string) => Number(String(s).replace(/[^\d]/g, "") || 0);
// created_at DB = "YYYY-MM-DD HH:MM:SS" giờ VN (salary_store: datetime('now','+7 hours')) → "18/7 19:25"
const tsLabel = (s?: string) => (s && s.length >= 16 ? `${Number(s.slice(8, 10))}/${Number(s.slice(5, 7))} ${s.slice(11, 16)}` : "");
const initialFilter = () => {
  const query = new URLSearchParams((window.location.hash.split("?")[1] || ""));
  const queryYM = query.get("ym") || "";
  const queryWid = Number(query.get("worker_id") || 0);
  return { ym: /^\d{4}-\d{2}$/.test(queryYM) ? queryYM : curYM(), wid: queryWid > 0 ? queryWid : null };
};

export function AllowanceEntry() {
  const initial = initialFilter();
  const [ym, setYm] = useState(initial.ym);
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [allows, setAllows] = useState<SalaryAllowance[] | null>(null);
  const [wid, setWid] = useState<number | null>(initial.wid);
  const [filterWid, setFilterWid] = useState<number | null>(initial.wid);
  const [amt, setAmt] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = () => {
    setAllows(null);
    setErr("");
    const request = filterWid ? listPayrollAllowances(ym, filterWid) : listAllAllowances(ym);
    request.then(setAllows).catch((e: any) => { setErr(e?.message || "Lỗi tải danh sách phụ cấp"); setAllows([]); });
  };
  useEffect(() => { listWorkers().then(({ workers }) => setWorkers(workers)).catch(() => {}); }, []);
  useEffect(() => { load(); }, [ym, filterWid]);

  const nameOf = (id: number) => workers.find((w) => w.id === id)?.name || `#${id}`;

  const submit = async () => {
    if (busy) return;
    if (!wid) { toast("Chọn thợ", "err"); return; }
    if (num(amt) <= 0) { toast("Nhập số tiền phụ cấp", "err"); return; }
    setBusy(true);
    try {
      await addPayrollAllowance(ym, wid, num(amt), note);
      toast(`Đã ghi phụ cấp ${money(num(amt))} cho ${nameOf(wid)}`, "ok");
      setAmt("");
      setNote("");
      load();
    } catch (e: any) { toast(e?.message || "Lỗi ghi phụ cấp", "err"); }
    finally { setBusy(false); }
  };

  const voidIt = async (id: number) => {
    const reason = await promptDialog("Lý do vô hiệu khoản phụ cấp này?", { placeholder: "VD: ghi nhầm số tiền…", okLabel: "Vô hiệu" });
    if (reason === null) return;
    if (!reason.trim()) { toast("Phải nhập lý do vô hiệu", "err"); return; }
    try { await voidPayrollAllowance(ym, id, reason.trim()); toast("Đã vô hiệu khoản phụ cấp", "ok"); load(); }
    catch (e: any) { toast(e?.message || "Lỗi vô hiệu", "err"); }
  };

  const list = (allows || []).slice().sort((a, b) => b.id - a.id);
  const active = list.filter((item) => !item.voided_at);
  const voidedCount = list.length - active.length;
  const total = active.reduce((sum, item) => sum + item.amount, 0);
  const wopts = workers.map((w) => ({ value: w.id, label: w.name }));

  const head = <PageHead fallback="#/home" title={<><Icon name="banknote" size={18} /> Nhập phụ cấp</>} sub="ghi phụ cấp cho thợ theo tháng" />;
  if (!isOffice()) return <div class="pr-page">{head}<EmptyState icon="🔒">Chỉ văn phòng.</EmptyState></div>;
  if (err) return <div class="pr-page">{head}<ErrorState msg={err} onRetry={load} /></div>;

  return (
    <div class="pr-page">
      {head}
      <div class="pr-monthbar">
        <button class="pr-mnav" onClick={() => setYm(shiftYM(ym, -1))} aria-label="Tháng trước">‹</button>
        <b>{ymLabel(ym)}</b>
        <button class="pr-mnav" onClick={() => setYm(shiftYM(ym, 1))} aria-label="Tháng sau">›</button>
      </div>

      <section class="card ua-create">
        <label class="card-label"><Icon name="plus" size={15} /> Ghi phụ cấp</label>
        <SelectPopup value={wid} options={wopts} onChange={(v) => setWid(Number(v))}
          searchable placeholder="Chọn thợ…" title="Chọn thợ" />
        <div class="ua-form">
          <input class="pw-input ua-amt-in" inputMode="numeric" placeholder="Số tiền phụ cấp" value={amt} onInput={(e: any) => setAmt(e.target.value)} />
          <input class="pw-input ua-note-in" placeholder="Nội dung phụ cấp" value={note} onInput={(e: any) => setNote(e.target.value)} />
        </div>
        <button class="btn primary block" disabled={busy} onClick={submit}>{busy ? "Đang ghi…" : "Ghi phụ cấp"}</button>
      </section>

      {allows === null ? <Loading /> : (
        <>
          {filterWid ? (
            <div class="ua-filter">
              <span>Đang lọc: <b>{nameOf(filterWid)}</b></span>
              <button class="btn small" onClick={() => setFilterWid(null)}>Xem tất cả</button>
            </div>
          ) : null}
          <div class="card pr-totals">
            <span>Tổng phụ cấp {ymLabel(ym).toLowerCase()} <b>{money(total)}</b> · {active.length} khoản{voidedCount ? ` · ${voidedCount} vô hiệu` : ""}</span>
          </div>
          {list.length === 0 ? <EmptyState icon="💵">Chưa có khoản phụ cấp nào trong tháng.</EmptyState> : (
            list.map((item) => (
              <div class={`card ua-row${item.voided_at ? " ua-voided" : ""}`} key={item.id}>
                <div class="ua-row-main">
                  <b>{nameOf(item.worker_id)}</b>
                  {item.voided_at ? <span class="ua-void-badge">VÔ HIỆU</span> : null}
                  {item.note ? <div class="muted small">{item.note}</div> : null}
                  {tsLabel(item.created_at) ? <div class="muted small ua-ts">tạo {tsLabel(item.created_at)}{item.created_by ? ` · ${item.created_by}` : ""}</div> : null}
                  {item.voided_at ? (
                    <div class="small ua-void-info">vô hiệu {tsLabel(item.voided_at)}{item.voided_by ? ` · ${item.voided_by}` : ""}{item.void_reason ? ` — ${item.void_reason}` : ""}</div>
                  ) : null}
                </div>
                <b class={`ua-amt${item.voided_at ? " ua-amt-voided" : ""}`}>{money(item.amount)}</b>
                {!item.voided_at ? <button class="pr-adv-del" onClick={() => voidIt(item.id)} aria-label="Vô hiệu">✕</button> : null}
              </div>
            ))
          )}
        </>
      )}
    </div>
  );
}
