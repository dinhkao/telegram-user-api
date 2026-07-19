// NHẬP ỨNG LƯƠNG (#/nhap-ung) — CHỈ văn phòng. Ghi nhanh tạm ứng cho thợ theo tháng:
// chọn thợ + số tiền + ngày + ghi chú → Ghi ứng. Danh sách các lần ứng trong tháng
// (mọi thợ) + tổng. Không xoá — VÔ HIỆU kèm lý do, dòng vẫn hiện (gạch ngang, ai/lúc
// nào/lý do). API: addPayrollAdvance/listAllAdvances/voidPayrollAdvance.
import { useEffect, useState } from "preact/hooks";
import {
  addPayrollAdvance, getMonthlyPayroll, isOffice, listAllAdvances, listPayrollAdvances, listWorkers, soVN, voidPayrollAdvance,
  type PayrollRow, type SalaryAdvance, type Worker,
} from "../api";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { SelectPopup } from "../ui/SelectPopup";
import { Loading, EmptyState } from "../ui/states";
import { toast, promptDialog } from "../ui/feedback";

const pad = (n: number) => String(n).padStart(2, "0");
const money = (n: number) => soVN(Math.round(n || 0));
const num = (s: string) => Number(String(s).replace(/[^\d]/g, "") || 0);
const curYM = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; };
const todayISO = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
const shiftYM = (ym: string, d: number) => { const [y, m] = ym.split("-").map(Number); const dt = new Date(y, m - 1 + d, 1); return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}`; };
const ymLabel = (ym: string) => { const [y, m] = ym.split("-"); return `Tháng ${Number(m)}/${y}`; };
const dmy = (s: string) => (s && s.length >= 10 ? `${s.slice(8, 10)}/${s.slice(5, 7)}` : s || "—");
// created_at DB = "YYYY-MM-DD HH:MM:SS" giờ VN (salary_store: datetime('now','+7 hours')) → "18/7 19:25"
const tsLabel = (s?: string) => (s && s.length >= 16 ? `${Number(s.slice(8, 10))}/${Number(s.slice(5, 7))} ${s.slice(11, 16)}` : "");
const initialFilter = () => {
  const query = new URLSearchParams((window.location.hash.split("?")[1] || ""));
  const queryYM = query.get("ym") || "";
  const queryWid = Number(query.get("worker_id") || 0);
  return { ym: /^\d{4}-\d{2}$/.test(queryYM) ? queryYM : curYM(), wid: queryWid > 0 ? queryWid : null };
};

export function AdvanceEntry() {
  const initial = initialFilter();
  const [ym, setYm] = useState(initial.ym);
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [advs, setAdvs] = useState<SalaryAdvance[] | null>(null);
  const [weeklyRows, setWeeklyRows] = useState<PayrollRow[]>([]);
  const [wid, setWid] = useState<number | null>(initial.wid);
  const [filterWid, setFilterWid] = useState<number | null>(initial.wid);
  const [amt, setAmt] = useState("");
  const [date, setDate] = useState(todayISO());
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => {
    setAdvs(null);
    const request = filterWid ? listPayrollAdvances(ym, filterWid) : listAllAdvances(ym);
    Promise.all([request, getMonthlyPayroll(ym)])
      .then(([items, payroll]) => {
        setAdvs(items);
        setWeeklyRows(payroll.workers.filter((row) => row.ung_weekly > 0 && (!filterWid || row.worker_id === filterWid)));
      })
      .catch(() => { setAdvs([]); setWeeklyRows([]); });
  };
  useEffect(() => { listWorkers().then(({ workers }) => setWorkers(workers)).catch(() => {}); }, []);
  useEffect(() => { load(); }, [ym, filterWid]);

  const nameOf = (id: number) => workers.find((w) => w.id === id)?.name || `#${id}`;

  const submit = async () => {
    if (busy) return;
    if (!wid) { toast("Chọn thợ", "err"); return; }
    if (num(amt) <= 0) { toast("Nhập số tiền ứng", "err"); return; }
    setBusy(true);
    try {
      await addPayrollAdvance(ym, wid, num(amt), date, note);
      toast(`Đã ghi ứng ${money(num(amt))} cho ${nameOf(wid)}`, "ok");
      setAmt(""); setNote("");
      load();
    } catch (e: any) { toast(e?.message || "Lỗi ghi ứng", "err"); }
    finally { setBusy(false); }
  };
  const voidIt = async (id: number) => {
    const reason = await promptDialog("Lý do vô hiệu lần ứng này?", { placeholder: "VD: ghi nhầm số tiền…", okLabel: "Vô hiệu" });
    if (reason === null) return;
    if (!reason.trim()) { toast("Phải nhập lý do vô hiệu", "err"); return; }
    try { await voidPayrollAdvance(ym, id, reason.trim()); toast("Đã vô hiệu khoản ứng", "ok"); load(); }
    catch (e: any) { toast(e?.message || "Lỗi vô hiệu", "err"); }
  };

  const list = (advs || []).slice().sort((a, b) => (b.adv_date || "").localeCompare(a.adv_date || "") || b.id - a.id);
  const active = list.filter((a) => !a.voided_at);
  const voidedCount = list.length - active.length;
  const total = active.reduce((s, a) => s + a.amount, 0) + weeklyRows.reduce((s, row) => s + row.ung_weekly, 0);
  const entryCount = active.length + weeklyRows.length;
  const wopts = workers.map((w) => ({ value: w.id, label: w.name }));

  const head = <PageHead fallback="#/home" title={<><Icon name="wallet" size={18} /> Nhập ứng lương</>} sub="ghi tạm ứng cho thợ theo tháng" />;
  if (!isOffice()) return <div class="pr-page">{head}<EmptyState icon="🔒">Chỉ văn phòng.</EmptyState></div>;

  return (
    <div class="pr-page">
      {head}
      <div class="pr-monthbar">
        <button class="pr-mnav" onClick={() => setYm(shiftYM(ym, -1))} aria-label="Tháng trước">‹</button>
        <b>{ymLabel(ym)}</b>
        <button class="pr-mnav" onClick={() => setYm(shiftYM(ym, 1))} aria-label="Tháng sau">›</button>
      </div>

      <section class="card ua-create">
        <label class="card-label">➕ Ghi ứng lương</label>
        <SelectPopup value={wid} options={wopts} onChange={(v) => setWid(Number(v))}
          searchable placeholder="Chọn thợ…" title="Chọn thợ" />
        <div class="ua-form">
          <input class="pw-input ua-amt-in" inputMode="numeric" placeholder="Số tiền ứng" value={amt} onInput={(e: any) => setAmt(e.target.value)} />
          <input class="pw-input" type="date" value={date} onInput={(e: any) => setDate(e.target.value)} />
          <input class="pw-input ua-note-in" placeholder="Ghi chú (tuỳ chọn)" value={note} onInput={(e: any) => setNote(e.target.value)} />
        </div>
        <button class="btn primary block" disabled={busy} onClick={submit}>{busy ? "Đang ghi…" : "Ghi ứng"}</button>
      </section>

      {advs === null ? <Loading /> : (
        <>
          {filterWid ? (
            <div class="ua-filter">
              <span>Đang lọc: <b>{nameOf(filterWid)}</b></span>
              <button class="btn small" onClick={() => setFilterWid(null)}>Xem tất cả</button>
            </div>
          ) : null}
          <div class="card pr-totals">
            <span>Tổng ứng {ymLabel(ym).toLowerCase()} <b class="t-danger">{money(total)}</b> · {entryCount} khoản{voidedCount ? ` · ${voidedCount} vô hiệu` : ""}</span>
          </div>
          {entryCount === 0 && voidedCount === 0 ? <EmptyState icon="💰">Chưa có khoản ứng nào trong tháng.</EmptyState> : (
            <>
              {weeklyRows.map((row) => (
                <div class="card ua-row" key={`weekly-${row.worker_id}`}>
                  <div class="ua-row-main">
                    <b>{row.name}</b>
                    <div class="muted small">Lương tuần tự động</div>
                  </div>
                  <b class="ua-amt t-danger">{money(row.ung_weekly)}</b>
                </div>
              ))}
              {list.map((a) => (
              <div class={`card ua-row${a.voided_at ? " ua-voided" : ""}`} key={a.id}>
                <div class="ua-row-main">
                  <b>{nameOf(a.worker_id)}</b>
                  <span class="muted small"> · {dmy(a.adv_date)}</span>
                  {a.voided_at ? <span class="ua-void-badge">VÔ HIỆU</span> : null}
                  {a.note ? <div class="muted small">{a.note}</div> : null}
                  {tsLabel(a.created_at) ? <div class="muted small ua-ts">tạo {tsLabel(a.created_at)}{a.created_by ? ` · ${a.created_by}` : ""}</div> : null}
                  {a.voided_at ? (
                    <div class="small ua-void-info">vô hiệu {tsLabel(a.voided_at)}{a.voided_by ? ` · ${a.voided_by}` : ""}{a.void_reason ? ` — ${a.void_reason}` : ""}</div>
                  ) : null}
                </div>
                <b class={`ua-amt ${a.voided_at ? "ua-amt-voided" : "t-danger"}`}>{money(a.amount)}</b>
                {!a.voided_at ? <button class="pr-adv-del" onClick={() => voidIt(a.id)} aria-label="Vô hiệu">✕</button> : null}
              </div>
              ))}
            </>
          )}
        </>
      )}
    </div>
  );
}
