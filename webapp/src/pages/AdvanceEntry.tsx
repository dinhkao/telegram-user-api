// NHẬP ỨNG LƯƠNG (#/nhap-ung) — CHỈ văn phòng. Ghi nhanh tạm ứng cho thợ theo tháng:
// chọn thợ + số tiền + ngày + ghi chú → Ghi ứng. Danh sách các lần ứng trong tháng
// (mọi thợ) + tổng. Không xoá — VÔ HIỆU kèm lý do, dòng vẫn hiện (gạch ngang, ai/lúc
// nào/lý do). Nút ✏️ = SỬA GHI CHÚ dòng chưa vô hiệu (số tiền/ngày bất biến — sai
// tiền thì vô hiệu rồi ghi lại).
// API: addPayrollAdvance/listAllAdvances/voidPayrollAdvance/setPayrollAdvanceNote.
// ⚠ ĐỒNG BỘ 2 CHỖ: cùng khoản ứng còn hiện ở panel P.cấp/Ứng của bảng lương tháng
// (detail/EntryPanel.tsx — popup ô bảng + view Thẻ). Thêm/sửa tính năng nào ở đây
// thì làm luôn bên đó, đừng để 1 bên có 1 bên không. Ô NHẬP TIỀN của cả 2 nơi là
// ui/MoneyEntryForm (ô to + đọc lại bằng chữ + chip cộng nhanh).
import { useEffect, useState } from "preact/hooks";
import {
  addPayrollAdvance, getMonthlyPayroll, isOffice, listAllAdvances, listPayrollAdvances, listWorkers,
  setPayrollAdvanceNote, soVN, voidPayrollAdvance,
  type PayrollRow, type SalaryAdvance, type Worker,
} from "../api";
import { EntryTable, type EntryRow } from "../detail/EntryTable";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { SelectPopup } from "../ui/SelectPopup";
import { MoneyEntryForm } from "../ui/MoneyEntryForm";
import { UNG_GOI_Y } from "../detail/EntryPanel";
import { useEntryView } from "../detail/useEntryView";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { toast, promptDialog } from "../ui/feedback";

import { moneyR as money, pad2 as pad, curYM, shiftYM, ymLabel, isoDate, dmy, tsLabel } from "../format";
const num = (s: string) => Number(String(s).replace(/[^\d]/g, "") || 0);
const todayISO = () => isoDate(new Date());
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
  const [err, setErr] = useState("");
  const [view, setView] = useEntryView("ua_view_ung");

  const load = () => {
    setAdvs(null);
    setErr("");
    const request = filterWid ? listPayrollAdvances(ym, filterWid) : listAllAdvances(ym);
    Promise.all([request, getMonthlyPayroll(ym)])
      .then(([items, payroll]) => {
        setAdvs(items);
        setWeeklyRows(payroll.workers.filter((row) => row.ung_weekly > 0 && (!filterWid || row.worker_id === filterWid)));
      })
      .catch((e: any) => { setErr(e?.message || "Lỗi tải danh sách ứng"); setAdvs([]); setWeeklyRows([]); });
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
  // Sửa GHI CHÚ (số tiền/ngày bất biến — ghi nhầm tiền thì vô hiệu rồi ghi lại)
  const editNote = async (a: SalaryAdvance) => {
    const next = await promptDialog(`Ghi chú lần ứng ${money(a.amount)} của ${nameOf(a.worker_id)}`, {
      initial: a.note || "", placeholder: "VD: ứng mua xe…", okLabel: "Lưu" });
    if (next === null || next.trim() === (a.note || "")) return;
    try { await setPayrollAdvanceNote(ym, a.id, next.trim()); toast("Đã lưu ghi chú", "ok"); load(); }
    catch (e: any) { toast(e?.message || "Lỗi lưu ghi chú", "err"); }
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
  if (err) return <div class="pr-page">{head}<ErrorState msg={err} onRetry={load} /></div>;

  return (
    <div class="pr-page">
      {head}
      <div class="pr-controlbar">
        <div class="pr-monthbar">
          <button class="pr-mnav" onClick={() => setYm(shiftYM(ym, -1))} aria-label="Tháng trước">‹</button>
          <b>{ymLabel(ym)}</b>
          <button class="pr-mnav" onClick={() => setYm(shiftYM(ym, 1))} aria-label="Tháng sau">›</button>
        </div>
        <div class="seg pr-viewseg" role="group" aria-label="Kiểu hiển thị">
          <button class={view === "card" ? "seg-btn active" : "seg-btn"} onClick={() => setView("card")}>
            <Icon name="grid" size={16} /> Thẻ</button>
          <button class={view === "table" ? "seg-btn active" : "seg-btn"} onClick={() => setView("table")}>
            <Icon name="menu" size={16} /> Bảng</button>
        </div>
      </div>

      <section class="card ua-create">
        <label class="card-label"><Icon name="plus" size={15} /> Ghi ứng lương</label>
        <MoneyEntryForm amount={amt} onAmount={setAmt} note={note} onNote={setNote}
          date={date} onDate={setDate}
          amountLabel="Số tiền ứng" submitLabel="Ghi ứng"
          notePlaceholder="VD: ứng mua xe…" noteSuggestions={UNG_GOI_Y}
          busy={busy} onSubmit={submit}
          before={<SelectPopup value={wid} options={wopts} onChange={(v) => setWid(Number(v))}
            searchable placeholder="Chọn thợ…" title="Chọn thợ" />} />
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
          {entryCount === 0 && voidedCount === 0 ? <EmptyState icon="💰">Chưa có khoản ứng nào trong tháng.</EmptyState>
           : view === "table" ? (
            <EntryTable sortKey="ua_sort_ung" emptyNote="chưa có ghi chú"
              rows={[
                ...weeklyRows.map((row): EntryRow => ({
                  key: `weekly-${row.worker_id}`, worker: row.name, ymd: "",
                  amount: row.ung_weekly, note: "Lương tuần tự động", auto: true,
                })),
                ...list.map((a): EntryRow => ({
                  key: String(a.id), worker: nameOf(a.worker_id), ymd: a.adv_date,
                  amount: a.amount, note: a.note, created: a.created_at, createdBy: a.created_by,
                  voidedAt: a.voided_at, voidedBy: a.voided_by, voidReason: a.void_reason,
                  onNote: () => editNote(a), onVoid: () => voidIt(a.id),
                })),
              ]} />
           ) : (
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
                  {a.note ? <div class="muted small">{a.note}</div>
                    : !a.voided_at ? <div class="muted small ua-note-empty">chưa có ghi chú</div> : null}
                  {tsLabel(a.created_at) ? <div class="muted small ua-ts">tạo {tsLabel(a.created_at)}{a.created_by ? ` · ${a.created_by}` : ""}</div> : null}
                  {a.voided_at ? (
                    <div class="small ua-void-info">vô hiệu {tsLabel(a.voided_at)}{a.voided_by ? ` · ${a.voided_by}` : ""}{a.void_reason ? ` — ${a.void_reason}` : ""}</div>
                  ) : null}
                </div>
                <b class={`ua-amt ${a.voided_at ? "ua-amt-voided" : "t-danger"}`}>{money(a.amount)}</b>
                {!a.voided_at ? (
                  <>
                    <button class="ua-note-edit" onClick={() => editNote(a)} aria-label="Sửa ghi chú" title="Sửa ghi chú"><Icon name="edit" size={15} /></button>
                    <button class="pr-adv-del" onClick={() => voidIt(a.id)} aria-label="Vô hiệu">✕</button>
                  </>
                ) : null}
              </div>
              ))}
            </>
          )}
        </>
      )}
    </div>
  );
}
