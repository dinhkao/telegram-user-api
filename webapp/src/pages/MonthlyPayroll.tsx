// BẢNG LƯƠNG THÁNG (#/luong-thang) — CHỈ văn phòng. Mỗi thợ 1 thẻ: loại lương (SP/thời
// gian, bấm đổi), lương (SP tự tính từ sản xuất; thời gian = 0 chờ chấm công), phụ cấp +
// thưởng (nhập tay/tháng), ứng lương (nhiều lần — mở xem/thêm/xoá), thực lãnh.
// API: getMonthlyPayroll/setPayrollAdjust/addPayrollAdvance/deletePayrollAdvance/updateWorker.
import { useEffect, useState } from "preact/hooks";
import {
  addPayrollAdvance, deletePayrollAdvance, getMonthlyPayroll, isOffice, listPayrollAdvances,
  setPayrollAdjust, soVN, updateWorker, type PayrollMonth, type PayrollRow, type SalaryAdvance,
} from "../api";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { toast, confirmDialog } from "../ui/feedback";

const pad = (n: number) => String(n).padStart(2, "0");
const money = (n: number) => soVN(Math.round(n || 0));
const num = (s: string) => Number(String(s).replace(/[^\d]/g, "") || 0);
const curYM = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; };
const shiftYM = (ym: string, d: number) => {
  const [y, m] = ym.split("-").map(Number);
  const dt = new Date(y, m - 1 + d, 1);
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}`;
};
const ymLabel = (ym: string) => { const [y, m] = ym.split("-"); return `Tháng ${Number(m)}/${y}`; };

export function MonthlyPayroll() {
  const [ym, setYm] = useState(curYM());
  const [data, setData] = useState<PayrollMonth | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [open, setOpen] = useState<number | null>(null);            // worker_id đang mở ứng
  const [advs, setAdvs] = useState<Record<number, SalaryAdvance[]>>({});
  const [view, setView] = useState<"table" | "card">("table");

  const load = () => {
    setLoading(true);
    getMonthlyPayroll(ym)
      .then((d) => { setData(d); setErr(""); setDraft({}); })
      .catch((e: any) => setErr(e?.message || "Lỗi tải bảng lương"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, [ym]);

  const apply = (d: PayrollMonth) => { setData(d); setDraft({}); };

  const saveAdjust = async (wid: number, field: "phu_cap" | "thuong", val: string) => {
    try { apply(await setPayrollAdjust(ym, wid, { [field]: num(val) } as any)); }
    catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); }
  };

  const toggleType = async (r: PayrollRow) => {
    const next = r.wage_type === "time" ? "product" : "time";
    try {
      await updateWorker(r.worker_id, { wage_type: next });
      toast(next === "time" ? "→ Lương thời gian" : "→ Lương sản phẩm", "ok");
      load();
    } catch (e: any) { toast(e?.message || "Lỗi đổi loại", "err"); }
  };

  // Nhận lương tuần: bật → tự động ứng = đúng lương SP (tính ở server)
  const toggleWeekly = async (r: PayrollRow) => {
    try {
      await updateWorker(r.worker_id, { weekly_salary: !r.weekly_salary });
      toast(!r.weekly_salary ? "BẬT nhận lương tuần" : "TẮT nhận lương tuần", "ok");
      load();
    } catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); }
  };

  const loadAdvances = async (wid: number) => {
    try { setAdvs((m) => ({ ...m, [wid]: [] })); const a = await listPayrollAdvances(ym, wid); setAdvs((m) => ({ ...m, [wid]: a })); }
    catch { /* im lặng */ }
  };
  const openAdv = (wid: number) => {
    if (open === wid) { setOpen(null); return; }
    setOpen(wid); loadAdvances(wid);
  };
  // Từ BẢNG bấm ô Ứng → chuyển sang THẺ của thợ đó + mở panel ứng để quản lý
  const gotoUng = (wid: number) => { setView("card"); setOpen(wid); loadAdvances(wid); };

  const totals = data?.totals;

  const head = (
    <PageHead fallback="#/home"
      title={<><Icon name="wallet" size={18} /> Bảng lương tháng</>}
      sub="lương SP tự tính + phụ cấp/thưởng/ứng theo tháng" />
  );
  if (!isOffice()) return <div class="pr-page">{head}<EmptyState icon="lock">Chỉ văn phòng.</EmptyState></div>;

  return (
    <div class="pr-page">
      {head}
      <div class="pr-monthbar">
        <button class="pr-mnav" onClick={() => setYm(shiftYM(ym, -1))} aria-label="Tháng trước">‹</button>
        <b>{ymLabel(ym)}</b>
        <button class="pr-mnav" onClick={() => setYm(shiftYM(ym, 1))} aria-label="Tháng sau">›</button>
      </div>

      {loading && !data ? <Loading />
        : err && !data ? <ErrorState msg={err} onRetry={load} />
        : !data || !data.workers.length ? <EmptyState icon="wallet">Chưa có nhân viên.</EmptyState>
        : (
          <>
            <div class="seg pr-viewseg">
              <button class={view === "table" ? "seg-btn active" : "seg-btn"} onClick={() => setView("table")}>📊 Bảng</button>
              <button class={view === "card" ? "seg-btn active" : "seg-btn"} onClick={() => setView("card")}>📇 Thẻ</button>
            </div>
            {totals && (
              <div class="card pr-totals">
                <span>Tổng thực lãnh <b>{money(totals.thuc_lanh)}</b></span>
                <span class="muted small">Lương {money(totals.luong)} · PC {money(totals.phu_cap)} · Thưởng {money(totals.thuong)} · Ứng {money(totals.ung)}</span>
              </div>
            )}
            {view === "table" ? (
              <PayrollTable data={data} draft={draft} setDraft={setDraft}
                saveAdjust={saveAdjust} toggleType={toggleType} toggleWeekly={toggleWeekly} onUng={gotoUng} />
            ) : (
              data.workers.map((r) => (
                <PayrollCard key={r.worker_id} r={r} ym={ym}
                  draft={draft} setDraft={setDraft} saveAdjust={saveAdjust}
                  toggleType={toggleType} toggleWeekly={toggleWeekly}
                  open={open === r.worker_id} onToggleAdv={() => openAdv(r.worker_id)}
                  advances={advs[r.worker_id]} apply={apply} setAdvs={setAdvs} />
              ))
            )}
          </>
        )}
    </div>
  );
}

function PayrollTable({ data, draft, setDraft, saveAdjust, toggleType, toggleWeekly, onUng }: {
  data: PayrollMonth; draft: Record<string, string>;
  setDraft: (f: (d: Record<string, string>) => Record<string, string>) => void;
  saveAdjust: (wid: number, field: "phu_cap" | "thuong", val: string) => void;
  toggleType: (r: PayrollRow) => void; toggleWeekly: (r: PayrollRow) => void; onUng: (wid: number) => void;
}) {
  const t = data.totals;
  const inp = (r: PayrollRow, field: "phu_cap" | "thuong") => {
    const k = `${r.worker_id}:${field}`;
    return (
      <input class="pw-input pr-tin" inputMode="numeric" placeholder="0"
        value={draft[k] !== undefined ? draft[k] : ((r as any)[field] ? String((r as any)[field]) : "")}
        onInput={(e: any) => setDraft((d) => ({ ...d, [k]: e.target.value }))}
        onBlur={(e: any) => saveAdjust(r.worker_id, field, e.target.value)}
        onKeyDown={(e: any) => { if (e.key === "Enter") e.target.blur(); }} />
    );
  };
  return (
    <div class="pr-table-wrap">
      <table class="pr-table">
        <thead>
          <tr>
            <th class="pr-sticky">Thợ</th><th>Loại</th><th>Lương&nbsp;tuần</th><th>Lương</th>
            <th>Phụ cấp</th><th>Thưởng</th><th>Ứng</th><th>Thực lãnh</th>
          </tr>
        </thead>
        <tbody>
          {data.workers.map((r) => {
            const isTime = r.wage_type === "time";
            return (
              <tr key={r.worker_id}>
                <td class="pr-sticky pr-td-name">{r.name}</td>
                <td class="pr-td-mid">
                  <button class={isTime ? "chip pr-type time" : "chip pr-type"} onClick={() => toggleType(r)}
                    title="Bấm để đổi loại lương">{isTime ? "TG" : "SP"}</button>
                </td>
                <td class="pr-td-mid">
                  <span class={r.weekly_salary ? "tgl on" : "tgl"} role="switch" aria-checked={r.weekly_salary}
                    onClick={() => toggleWeekly(r)} style="cursor:pointer" title="Nhận lương tuần"><span class="tgl-knob" /></span>
                </td>
                <td class="pr-num">{isTime ? "0" : money(r.luong)}</td>
                <td class="pr-td-in">{inp(r, "phu_cap")}</td>
                <td class="pr-td-in">{inp(r, "thuong")}</td>
                <td class="pr-num">
                  <button class="pr-ung-btn" onClick={() => onUng(r.worker_id)} title="Quản lý ứng lương">
                    {money(r.ung)}{r.adv_count ? <sup> {r.adv_count}</sup> : null}
                  </button>
                </td>
                <td class={r.thuc_lanh < 0 ? "pr-num t-danger" : "pr-num pr-net-td"}>{money(r.thuc_lanh)}</td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr>
            <td class="pr-sticky pr-td-name">Tổng</td><td></td><td></td>
            <td class="pr-num">{money(t.luong)}</td>
            <td class="pr-num">{money(t.phu_cap)}</td>
            <td class="pr-num">{money(t.thuong)}</td>
            <td class="pr-num">{money(t.ung)}</td>
            <td class="pr-num pr-net-td">{money(t.thuc_lanh)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function PayrollCard({ r, ym, draft, setDraft, saveAdjust, toggleType, toggleWeekly, open, onToggleAdv, advances, apply, setAdvs }: {
  r: PayrollRow; ym: string; draft: Record<string, string>;
  setDraft: (f: (d: Record<string, string>) => Record<string, string>) => void;
  saveAdjust: (wid: number, field: "phu_cap" | "thuong", val: string) => void;
  toggleType: (r: PayrollRow) => void; toggleWeekly: (r: PayrollRow) => void;
  open: boolean; onToggleAdv: () => void; advances?: SalaryAdvance[];
  apply: (d: PayrollMonth) => void; setAdvs: (f: (m: Record<number, SalaryAdvance[]>) => Record<number, SalaryAdvance[]>) => void;
}) {
  const [amt, setAmt] = useState("");
  const [advDate, setAdvDate] = useState("");
  const [advNote, setAdvNote] = useState("");
  const kPc = `${r.worker_id}:phu_cap`, kTh = `${r.worker_id}:thuong`;
  const isTime = r.wage_type === "time";

  const addAdv = async () => {
    const a = num(amt);
    if (a <= 0) { toast("Nhập số tiền ứng", "err"); return; }
    try {
      apply(await addPayrollAdvance(ym, r.worker_id, a, advDate, advNote));
      setAmt(""); setAdvNote("");
      const list = await listPayrollAdvances(ym, r.worker_id);
      setAdvs((m) => ({ ...m, [r.worker_id]: list }));
    } catch (e: any) { toast(e?.message || "Lỗi thêm ứng", "err"); }
  };
  const delAdv = async (id: number) => {
    if (!(await confirmDialog("Xoá lần ứng này?"))) return;
    try {
      apply(await deletePayrollAdvance(ym, id));
      setAdvs((m) => ({ ...m, [r.worker_id]: (m[r.worker_id] || []).filter((x) => x.id !== id) }));
    } catch (e: any) { toast(e?.message || "Lỗi xoá", "err"); }
  };

  return (
    <section class="card pr-card">
      <div class="pr-top">
        <div class="pr-name">
          {r.name}
          <button class={isTime ? "chip pr-type time" : "chip pr-type"} onClick={() => toggleType(r)}
            title="Bấm để đổi loại lương">{isTime ? "Thời gian" : "Sản phẩm"}</button>
        </div>
        <b class="pr-net">{money(r.thuc_lanh)}</b>
      </div>
      <div class="pr-line muted small">
        Lương {isTime ? <span title="Chờ chấm công">0 <i>(chờ chấm công)</i></span> : <b>{money(r.luong)}</b>}
      </div>
      <div class="pr-wk-row">
        <span>Nhận lương tuần {r.weekly_salary && r.ung_weekly > 0 ? <span class="muted small">(tự ứng {money(r.ung_weekly)})</span> : null}</span>
        <span class={r.weekly_salary ? "tgl on" : "tgl"} role="switch" aria-checked={r.weekly_salary}
          onClick={() => toggleWeekly(r)} style="cursor:pointer"><span class="tgl-knob" /></span>
      </div>
      <div class="pr-edits">
        <label>Phụ cấp
          <input class="pw-input" inputMode="numeric" placeholder="0"
            value={draft[kPc] !== undefined ? draft[kPc] : (r.phu_cap ? String(r.phu_cap) : "")}
            onInput={(e: any) => setDraft((d) => ({ ...d, [kPc]: e.target.value }))}
            onBlur={(e: any) => saveAdjust(r.worker_id, "phu_cap", e.target.value)}
            onKeyDown={(e: any) => { if (e.key === "Enter") e.target.blur(); }} />
        </label>
        <label>Thưởng
          <input class="pw-input" inputMode="numeric" placeholder="0"
            value={draft[kTh] !== undefined ? draft[kTh] : (r.thuong ? String(r.thuong) : "")}
            onInput={(e: any) => setDraft((d) => ({ ...d, [kTh]: e.target.value }))}
            onBlur={(e: any) => saveAdjust(r.worker_id, "thuong", e.target.value)}
            onKeyDown={(e: any) => { if (e.key === "Enter") e.target.blur(); }} />
        </label>
      </div>
      <button class="pr-adv-toggle" onClick={onToggleAdv}>
        <span>Ứng: <b class={r.ung ? "t-danger" : ""}>{money(r.ung)}</b> {r.adv_count ? <span class="muted small">({r.adv_count} lần)</span> : null}</span>
        <span class="muted">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div class="pr-adv">
          {r.weekly_salary && r.ung_weekly > 0 && (
            <div class="pr-adv-row pr-adv-weekly">
              <span class="muted small">Lương tuần</span>
              <b>{money(r.ung_weekly)}</b>
              <span class="muted small pr-adv-note">tự động = lương SP</span>
            </div>
          )}
          {(advances || []).map((a) => (
            <div class="pr-adv-row" key={a.id}>
              <span class="muted small">{a.adv_date || "—"}</span>
              <b>{money(a.amount)}</b>
              <span class="muted small pr-adv-note">{a.note}</span>
              <button class="pr-adv-del" onClick={() => delAdv(a.id)} aria-label="Xoá">✕</button>
            </div>
          ))}
          {advances && !advances.length ? <div class="muted small">Chưa có lần ứng nào.</div> : null}
          <div class="pr-adv-add">
            <input class="pw-input" inputMode="numeric" placeholder="Số tiền ứng" value={amt} onInput={(e: any) => setAmt(e.target.value)} />
            <input class="pw-input" type="date" value={advDate} onInput={(e: any) => setAdvDate(e.target.value)} />
            <input class="pw-input pr-adv-note-in" placeholder="Ghi chú" value={advNote} onInput={(e: any) => setAdvNote(e.target.value)} />
            <button class="btn primary" onClick={addAdv}>Thêm</button>
          </div>
        </div>
      )}
    </section>
  );
}
