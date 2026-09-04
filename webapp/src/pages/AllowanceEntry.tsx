// NHẬP PHỤ CẤP (#/nhap-phu-cap) — CHỈ văn phòng. Ghi phụ cấp cho thợ theo tháng.
// Không xoá — VÔ HIỆU kèm lý do, dòng vẫn hiện (gạch ngang, ai/lúc nào/lý do).
// Nút ✏️ = SỬA NỘI DUNG khoản chưa vô hiệu (số tiền bất biến — sai tiền thì vô hiệu
// rồi ghi lại). API: setPayrollAllowanceNote.
// ⚠ ĐỒNG BỘ 2 CHỖ: cùng khoản phụ cấp còn hiện ở panel P.cấp/Ứng của bảng lương tháng
// (detail/EntryPanel.tsx — popup ô bảng + view Thẻ). Thêm/sửa tính năng nào ở đây
// thì làm luôn bên đó, đừng để 1 bên có 1 bên không. Ô NHẬP TIỀN của cả 2 nơi là
// ui/MoneyEntryForm (ô to + đọc lại bằng chữ + chip cộng nhanh).
import { useEffect, useState } from "preact/hooks";
import {
  addPayrollAllowance, getMonthlyPayroll, isOffice, listAllAllowances, listPayrollAllowances, listWorkers,
  setPayrollAllowanceNote, setPayrollAllowancePrintNote, soVN, voidPayrollAllowance,
  type PayrollRow, type SalaryAllowance, type Worker,
} from "../api";
import { EntryTable, type EntryRow } from "../detail/EntryTable";
import { useEntryView } from "../detail/useEntryView";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { SelectPopup } from "../ui/SelectPopup";
import { MoneyEntryForm } from "../ui/MoneyEntryForm";
import { PC_GOI_Y, type PctInfo } from "../detail/EntryPanel";
import { PrevAllowances, allowCalcOf } from "../detail/PrevAllowances";
import { pctBaseOf } from "../detail/PayrollCellPopup";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { toast, promptDialog } from "../ui/feedback";

import { moneyR as money, pad2 as pad, curYM, shiftYM, ymLabel, isoDate, tsLabel } from "../format";
const num = (s: string) => Number(String(s).replace(/[^\d]/g, "") || 0);
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
  const [pnote, setPnote] = useState("");   // chữ in trên phiếu lương của khoản
  // Bảng lương tháng — chỉ để lấy GỐC tính phụ cấp theo % của thợ đang chọn
  // (thợ SP → lương sản phẩm, thợ TG → lương ngày công). Xem detail/EntryPanel.
  const [payroll, setPayroll] = useState<PayrollRow[]>([]);
  const [pct, setPct] = useState<PctInfo>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [view, setView] = useEntryView("ua_view_pc");

  const load = () => {
    setAllows(null);
    setErr("");
    const request = filterWid ? listPayrollAllowances(ym, filterWid) : listAllAllowances(ym);
    request.then(setAllows).catch((e: any) => { setErr(e?.message || "Lỗi tải danh sách phụ cấp"); setAllows([]); });
  };
  useEffect(() => { listWorkers().then(({ workers }) => setWorkers(workers)).catch(() => {}); }, []);
  useEffect(() => { load(); }, [ym, filterWid]);
  useEffect(() => { getMonthlyPayroll(ym).then((d) => setPayroll(d.workers)).catch(() => setPayroll([])); }, [ym]);

  const nameOf = (id: number) => workers.find((w) => w.id === id)?.name || `#${id}`;

  const submit = async () => {
    if (busy) return;
    if (!wid) { toast("Chọn thợ", "err"); return; }
    if (num(amt) <= 0) { toast("Nhập số tiền phụ cấp", "err"); return; }
    setBusy(true);
    try {
      // nhập theo % thì ghi luôn cách tính vào nội dung (DB chỉ lưu SỐ TIỀN chốt)
      // có công thức thì lưu công thức, số tiền sẽ tự tính lại theo lương gốc
      await addPayrollAllowance(ym, wid, num(amt), note,
        pct ? { kind: pct.kind, value: pct.n } : null, pnote);
      toast(`Đã ghi phụ cấp ${money(num(amt))} cho ${nameOf(wid)}`, "ok");
      setAmt("");
      setNote("");
      setPnote("");
      setPct(null);
      load();
    } catch (e: any) { toast(e?.message || "Lỗi ghi phụ cấp", "err"); }
    finally { setBusy(false); }
  };

  // ⧉ Chép 1 khoản của tháng trước sang tháng đang xem (detail/PrevAllowances —
  // khoản theo công thức chép cả công thức, số tự tính lại theo lương tháng này)
  const copyPrev = async (item: SalaryAllowance) => {
    if (!wid) return;
    try {
      await addPayrollAllowance(ym, wid, item.amount, item.note, allowCalcOf(item), item.print_note);
      toast(`Đã chép phụ cấp ${money(item.amount)} cho ${nameOf(wid)}`, "ok");
      load();
    } catch (e: any) { toast(e?.message || "Lỗi chép phụ cấp", "err"); }
  };

  // Sửa NỘI DUNG/ghi chú khoản phụ cấp (số tiền bất biến — sai tiền thì vô hiệu rồi ghi lại)
  const editNote = async (item: SalaryAllowance) => {
    const next = await promptDialog(`Nội dung khoản phụ cấp ${money(item.amount)} của ${nameOf(item.worker_id)}`, {
      initial: item.note || "", placeholder: "VD: ăn trưa, xăng xe…", okLabel: "Lưu" });
    if (next === null || next.trim() === (item.note || "")) return;
    try { await setPayrollAllowanceNote(ym, item.id, next.trim()); toast("Đã lưu nội dung", "ok"); load(); }
    catch (e: any) { toast(e?.message || "Lỗi lưu nội dung", "err"); }
  };

  // 🖨 CHỮ IN TRÊN PHIẾU của khoản (rỗng = phiếu in nội dung khoản + công thức)
  const editPrintNote = async (item: SalaryAllowance) => {
    const cur = item.print_note || "";
    const next = await promptDialog(
      `Chữ in trên phiếu lương cho khoản ${money(item.amount)} của ${nameOf(item.worker_id)}\nĐể trống = in theo nội dung khoản.`,
      { initial: cur, placeholder: "VD: Phụ cấp tháng 7", okLabel: "Lưu" });
    if (next === null || next.trim() === cur) return;
    try { await setPayrollAllowancePrintNote(ym, item.id, next.trim()); toast("Đã lưu chữ in trên phiếu", "ok"); load(); }
    catch (e: any) { toast(e?.message || "Lỗi lưu chữ in", "err"); }
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
        <label class="card-label"><Icon name="plus" size={15} /> Ghi phụ cấp</label>
        <MoneyEntryForm amount={amt} onAmount={setAmt} note={note} onNote={setNote}
          printNote={pnote} onPrintNote={setPnote}
          amountLabel="Số tiền phụ cấp" submitLabel="Ghi phụ cấp"
          noteLabel="Nội dung phụ cấp" notePlaceholder="VD: ăn trưa, xăng xe…"
          noteSuggestions={PC_GOI_Y} busy={busy} onSubmit={submit}
          pctBase={(() => { const row = wid ? payroll.find((p) => p.worker_id === wid) : null;
            return row ? pctBaseOf(row) : null; })()}
          dayBase={(() => { const row = wid ? payroll.find((p) => p.worker_id === wid) : null;
            return row ? { days: row.cong || 0 } : null; })()}
          onPct={setPct}
          before={<SelectPopup value={wid} options={wopts} onChange={(v) => setWid(Number(v))}
            searchable placeholder="Chọn thợ…" title="Chọn thợ" />} />
        {/* Khoản của 3 tháng trước → chép nhanh sang tháng đang xem (khi đã chọn thợ) */}
        {wid ? <PrevAllowances key={`${ym}-${wid}`} ym={ym} wid={wid} onCopy={copyPrev} /> : null}
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
          {list.length === 0 ? <EmptyState icon="💵">Chưa có khoản phụ cấp nào trong tháng.</EmptyState>
           : view === "table" ? (
            <EntryTable sortKey="ua_sort_pc" emptyNote="chưa ghi nội dung"
              rows={list.map((item): EntryRow => ({
                key: String(item.id), worker: nameOf(item.worker_id), ymd: "",
                amount: item.amount,
                // khoản theo CÔNG THỨC: ghi kèm công thức để bảng nói rõ số ở đâu ra
                // chữ IN TRÊN PHIẾU (nếu có) hiện ngay để đối chiếu với phiếu phát ra
                note: [item.note, item.calc_label, item.print_note ? `🖨 ${item.print_note}` : ""]
                  .filter(Boolean).join(" · "),
                created: item.created_at, createdBy: item.created_by,
                voidedAt: item.voided_at, voidedBy: item.voided_by, voidReason: item.void_reason,
                onNote: () => editNote(item), onVoid: () => voidIt(item.id),
                onPrintNote: () => editPrintNote(item),
              }))} />
           ) : (
            list.map((item) => (
              <div class={`card ua-row${item.voided_at ? " ua-voided" : ""}`} key={item.id}>
                <div class="ua-row-main">
                  <b>{nameOf(item.worker_id)}</b>
                  {item.voided_at ? <span class="ua-void-badge">VÔ HIỆU</span> : null}
                  {item.note ? <div class="muted small">{item.note}</div>
                    : !item.voided_at ? <div class="muted small ua-note-empty">chưa ghi nội dung</div> : null}
                  {item.print_note ? <div class="ua-print-note">🖨 in trên phiếu: <b>{item.print_note}</b></div> : null}
                  {tsLabel(item.created_at) ? <div class="muted small ua-ts">tạo {tsLabel(item.created_at)}{item.created_by ? ` · ${item.created_by}` : ""}</div> : null}
                  {item.voided_at ? (
                    <div class="small ua-void-info">vô hiệu {tsLabel(item.voided_at)}{item.voided_by ? ` · ${item.voided_by}` : ""}{item.void_reason ? ` — ${item.void_reason}` : ""}</div>
                  ) : null}
                </div>
                <b class={`ua-amt${item.voided_at ? " ua-amt-voided" : ""}`}>{money(item.amount)}</b>
                {!item.voided_at ? (
                  <>
                    <button class="ua-note-edit" onClick={() => editNote(item)} aria-label="Sửa nội dung" title="Sửa nội dung"><Icon name="edit" size={15} /></button>
                    <button class="ua-note-edit" onClick={() => editPrintNote(item)} aria-label="Sửa chữ in trên phiếu" title="Sửa chữ in trên phiếu lương">🖨</button>
                    <button class="pr-adv-del" onClick={() => voidIt(item.id)} aria-label="Vô hiệu">✕</button>
                  </>
                ) : null}
              </div>
            ))
          )}
        </>
      )}
    </div>
  );
}
