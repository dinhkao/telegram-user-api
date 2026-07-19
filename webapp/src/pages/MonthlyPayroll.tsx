// BẢNG LƯƠNG THÁNG (#/luong-thang) — CHỈ văn phòng. Mỗi thợ: loại lương (SP/thời gian),
// lương (SP tự tính; thời gian = 0 chờ chấm công), nhận lương tuần (theo tháng),
// PHỤ CẤP nhiều khoản, ỨNG lương nhiều lần → thực lãnh. Phụ cấp + ứng quản lý giống
// nhau (panel thêm/VÔ HIỆU khoản — không xoá, dòng giữ lại kèm ai/lúc nào/lý do).
// API: getMonthlyPayroll + payroll allowance/advance.
// (Cột THƯỞNG bỏ 2026-07-19 — phụ cấp nhiều khoản có nhãn đã thay thế; backend giữ
// field thuong cho tương thích, compute vẫn cộng nếu tháng cũ có dữ liệu.)
import { useEffect, useState } from "preact/hooks";
import {
  addPayrollAdvance, addPayrollAllowance, getMonthlyPayroll, isOffice,
  listPayrollAdvances, listPayrollAllowances, setPayrollAdjust, soVN, updateWorker,
  voidPayrollAdvance, voidPayrollAllowance,
  type PayrollMonth, type PayrollRow, type SalaryAdvance, type SalaryAllowance,
} from "../api";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { toast, promptDialog } from "../ui/feedback";

const pad = (n: number) => String(n).padStart(2, "0");
const money = (n: number) => soVN(Math.round(n || 0));
// Số RÚT GỌN cho BẢNG (để vừa màn hình, header sticky thuần CSS): 5.200.000→"5,2tr",
// 300.000→"300k". Làm tròn 1 số thập phân — số chính xác xem ở thẻ / chi tiết thợ.
const moneyShort = (n: number) => {
  const v = Math.round(n || 0);
  if (v === 0) return "0";
  const sign = v < 0 ? "−" : "";
  const a = Math.abs(v);
  if (a >= 1_000_000) return sign + (Math.round(a / 100_000) / 10).toString().replace(".", ",") + "tr";
  if (a >= 1_000) return sign + (Math.round(a / 100) / 10).toString().replace(".", ",") + "k";
  return sign + a;
};
const num = (s: string) => Number(String(s).replace(/[^\d]/g, "") || 0);
const curYM = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; };
const shiftYM = (ym: string, d: number) => {
  const [y, m] = ym.split("-").map(Number);
  const dt = new Date(y, m - 1 + d, 1);
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}`;
};
const ymLabel = (ym: string) => { const [y, m] = ym.split("-"); return `Tháng ${Number(m)}/${y}`; };
const initials = (name: string) => name.trim().split(/\s+/).slice(-2).map((part) => part[0] || "").join("").toUpperCase();

// Ghi nhớ theo PHIÊN (module scope, reset khi tải lại): THÁNG đang xem (back về
// giữ nguyên tháng). Kiểu hiển thị lưu localStorage (mặc định BẢNG). Vị trí cuộn
// DỌC do useScrollMemory toàn cục lo (bảng cuộn theo trang, không còn cuộn ngang).
const VIEW_KEY = "payroll_view";
let _savedYm: string | null = null;
const loadView = (): "table" | "card" => {
  try { return localStorage.getItem(VIEW_KEY) === "card" ? "card" : "table"; } catch { return "table"; }
};

export function MonthlyPayroll() {
  const [ym, setYm] = useState(() => _savedYm || curYM());
  const [data, setData] = useState<PayrollMonth | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [view, setViewState] = useState<"table" | "card">(loadView);
  const setView = (v: "table" | "card") => { setViewState(v); try { localStorage.setItem(VIEW_KEY, v); } catch { /**/ } };
  const [openUng, setOpenUng] = useState<number | null>(null);
  const [openPc, setOpenPc] = useState<number | null>(null);
  const [advs, setAdvs] = useState<Record<number, SalaryAdvance[]>>({});
  const [allows, setAllows] = useState<Record<number, SalaryAllowance[]>>({});

  const load = () => {
    setLoading(true);
    getMonthlyPayroll(ym)
      .then((d) => { setData(d); setErr(""); })
      .catch((e: any) => setErr(e?.message || "Lỗi tải bảng lương"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, [ym]);
  useEffect(() => { _savedYm = ym; }, [ym]);   // nhớ tháng đang xem cho lần quay lại

  const apply = (d: PayrollMonth) => setData(d);

  const toggleType = async (r: PayrollRow) => {
    const next = r.wage_type === "time" ? "product" : "time";
    try { await updateWorker(r.worker_id, { wage_type: next }); toast(next === "time" ? "→ Lương thời gian" : "→ Lương sản phẩm", "ok"); load(); }
    catch (e: any) { toast(e?.message || "Lỗi đổi loại", "err"); }
  };
  const toggleWeekly = async (r: PayrollRow) => {
    try { apply(await setPayrollAdjust(ym, r.worker_id, { weekly: !r.weekly }));
      toast(!r.weekly ? "BẬT nhận lương tuần (tháng này)" : "TẮT nhận lương tuần", "ok"); }
    catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); }
  };

  const loadAdvances = async (wid: number) => {
    try { setAdvs((m) => ({ ...m, [wid]: [] })); const a = await listPayrollAdvances(ym, wid); setAdvs((m) => ({ ...m, [wid]: a })); } catch { /**/ }
  };
  const loadAllowances = async (wid: number) => {
    try { setAllows((m) => ({ ...m, [wid]: [] })); const a = await listPayrollAllowances(ym, wid); setAllows((m) => ({ ...m, [wid]: a })); } catch { /**/ }
  };
  const toggleUng = (wid: number) => { if (openUng === wid) { setOpenUng(null); return; } setOpenUng(wid); loadAdvances(wid); };
  const togglePc = (wid: number) => { if (openPc === wid) { setOpenPc(null); return; } setOpenPc(wid); loadAllowances(wid); };
  const totals = data?.totals;
  const head = (
    <PageHead fallback="#/home"
      title={<><Icon name="wallet" size={18} /> Bảng lương tháng</>}
      sub="lương SP tự tính + phụ cấp/ứng theo tháng" />
  );
  if (!isOffice()) return <div class="pr-page">{head}<EmptyState icon="🔒">Chỉ văn phòng.</EmptyState></div>;

  return (
    <div class="pr-page pr-payroll-page">
      {head}
      <div class="pr-controlbar">
        <div class="pr-monthbar">
          <button class="pr-mnav previous" onClick={() => setYm(shiftYM(ym, -1))} aria-label="Tháng trước"><Icon name="chevronRight" size={18} /></button>
          <div class="pr-period">
            <span>Kỳ lương</span>
            <b>{ymLabel(ym)}</b>
          </div>
          <button class="pr-mnav" onClick={() => setYm(shiftYM(ym, 1))} aria-label="Tháng sau"><Icon name="chevronRight" size={18} /></button>
        </div>
        <div class="seg pr-viewseg" role="group" aria-label="Kiểu hiển thị">
          <button class={view === "table" ? "seg-btn active" : "seg-btn"} onClick={() => setView("table")}><Icon name="menu" size={16} /> Bảng</button>
          <button class={view === "card" ? "seg-btn active" : "seg-btn"} onClick={() => setView("card")}><Icon name="grid" size={16} /> Thẻ</button>
        </div>
      </div>

      {loading && !data ? <Loading />
        : err && !data ? <ErrorState msg={err} onRetry={load} />
        : !data || !data.workers.length ? <EmptyState icon="💰">Chưa có nhân viên.</EmptyState>
        : (
          <>
            {totals && (
              <section class="pr-summary" aria-label="Tổng quan bảng lương">
                <div class="pr-summary-net">
                  <span>Thực lãnh toàn bộ</span>
                  <strong>{money(totals.thuc_lanh)}</strong>
                  <small>{data.workers.length} nhân viên · {data.workers.filter((r) => r.weekly).length} nhận lương tuần</small>
                </div>
                <div class="pr-summary-breakdown">
                  <div class="pr-stat gross"><span>Lương gốc</span><b>{money(totals.luong)}</b></div>
                  <a class="pr-stat allowance" href={`#/nhap-phu-cap?ym=${encodeURIComponent(ym)}`}><span>Phụ cấp</span><b>+{money(totals.phu_cap)}</b></a>
                  <a class="pr-stat advance" href={`#/nhap-ung?ym=${encodeURIComponent(ym)}`}><span>Đã ứng</span><b>−{money(totals.ung)}</b></a>
                </div>
              </section>
            )}
            {view === "table" ? (
              <PayrollTable data={data} toggleType={toggleType} toggleWeekly={toggleWeekly} />
            ) : (
              <div class="pr-card-grid">
                {data.workers.map((r) => (
                  <PayrollCard key={r.worker_id} r={r} ym={ym}
                    toggleType={toggleType} toggleWeekly={toggleWeekly}
                    openUng={openUng === r.worker_id} onToggleUng={() => toggleUng(r.worker_id)} advances={advs[r.worker_id]}
                    openPc={openPc === r.worker_id} onTogglePc={() => togglePc(r.worker_id)} allowances={allows[r.worker_id]}
                    apply={apply} setAdvs={setAdvs} setAllows={setAllows} />
                ))}
              </div>
            )}
          </>
        )}
    </div>
  );
}

// Panel liệt kê + thêm/VÔ HIỆU KHOẢN (dùng cho cả phụ cấp lẫn ứng). Khoản vô hiệu vẫn
// hiện (gạch ngang + ai/lý do), không tính vào tổng. extra = dòng đọc-thêm ở đầu.
function EntryPanel({ entries, showDate, addPlaceholder, onAdd, onDel, extra }: {
  entries?: { id: number; amount: number; note: string; adv_date?: string; voided_at?: string; voided_by?: string; void_reason?: string }[];
  showDate?: boolean; addPlaceholder: string;
  onAdd: (amount: number, note: string, date: string) => void; onDel: (id: number) => void; extra?: any;
}) {
  const [amt, setAmt] = useState("");
  const [date, setDate] = useState("");
  const [note, setNote] = useState("");
  const add = () => {
    const a = num(amt);
    if (a <= 0) { toast("Nhập số tiền", "err"); return; }
    onAdd(a, note, date); setAmt(""); setNote("");
  };
  return (
    <div class="pr-adv">
      {extra}
      {(entries || []).map((e) => (
        <div class={`pr-adv-row${e.voided_at ? " ua-voided" : ""}`} key={e.id}>
          {showDate ? <span class="muted small">{e.adv_date || "—"}</span> : null}
          <b class={e.voided_at ? "ua-amt-voided" : ""}>{money(e.amount)}</b>
          <span class="muted small pr-adv-note">
            {e.note}
            {e.voided_at ? <span class="ua-void-info"> · vô hiệu{e.voided_by ? ` bởi ${e.voided_by}` : ""}{e.void_reason ? ` — ${e.void_reason}` : ""}</span> : null}
          </span>
          {!e.voided_at ? <button class="pr-adv-del" onClick={() => onDel(e.id)} aria-label="Vô hiệu">✕</button> : null}
        </div>
      ))}
      {entries && !entries.length ? <div class="muted small">Chưa có khoản nào.</div> : null}
      <div class="pr-adv-add">
        <input class="pw-input" inputMode="numeric" placeholder={addPlaceholder} value={amt} onInput={(e: any) => setAmt(e.target.value)} />
        {showDate ? <input class="pw-input" type="date" value={date} onInput={(e: any) => setDate(e.target.value)} /> : null}
        <input class="pw-input pr-adv-note-in" placeholder="Ghi chú" value={note} onInput={(e: any) => setNote(e.target.value)} />
        <button class="btn primary" onClick={add}>Thêm</button>
      </div>
    </div>
  );
}

function PayrollTable({ data, toggleType, toggleWeekly }: {
  data: PayrollMonth;
  toggleType: (r: PayrollRow) => void; toggleWeekly: (r: PayrollRow) => void;
}) {
  const t = data.totals;
  return (
    <div class="pr-table-wrap">
      <table class="pr-table">
        <thead>
          <tr>
            <th class="pr-sticky">Thợ</th><th>Loại</th><th>Tuần</th><th>Lương</th>
            <th>P.cấp</th><th>Ứng</th><th>Lãnh</th>
          </tr>
        </thead>
        <tbody>
          {data.workers.map((r) => {
            const isTime = r.wage_type === "time";
            return (
              <tr key={r.worker_id}>
                <td class="pr-sticky pr-td-name">
                  <a class="pr-worker" href={`#/sx-tho/${encodeURIComponent(r.name)}`}>
                    <span class="pr-avatar">{initials(r.name)}</span>
                    <span>{r.name}</span>
                  </a>
                </td>
                <td class="pr-td-mid">
                  <button class={isTime ? "chip pr-type time" : "chip pr-type"} onClick={() => toggleType(r)}
                    title="Bấm để đổi loại lương">{isTime ? "TG" : "SP"}</button>
                </td>
                <td class="pr-td-mid">
                  <span class={r.weekly ? "tgl on" : "tgl"} role="switch" aria-checked={r.weekly}
                    onClick={() => toggleWeekly(r)} style="cursor:pointer" title="Nhận lương tuần"><span class="tgl-knob" /></span>
                </td>
                <td class={isTime || !r.luong ? "pr-num is-zero" : "pr-num"}>{isTime ? "0" : moneyShort(r.luong)}</td>
                <td class="pr-num">
                  <a class="pr-ung-btn" href={`#/nhap-phu-cap?ym=${encodeURIComponent(data.ym)}&worker_id=${r.worker_id}`} title="Mở phụ cấp của nhân viên">
                    {moneyShort(r.phu_cap)}{r.pc_count ? <sup> {r.pc_count}</sup> : null}
                  </a>
                </td>
                <td class="pr-num">
                  <a class="pr-ung-btn" href={`#/nhap-ung?ym=${encodeURIComponent(data.ym)}&worker_id=${r.worker_id}`} title="Mở ứng lương của nhân viên">
                    {moneyShort(r.ung)}{r.adv_count ? <sup> {r.adv_count}</sup> : null}
                  </a>
                </td>
                <td class={r.thuc_lanh < 0 ? "pr-num pr-net-td t-danger" : "pr-num pr-net-td"}>{moneyShort(r.thuc_lanh)}</td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr>
            <td class="pr-sticky pr-td-name">Tổng</td><td></td><td></td>
            <td class="pr-num">{moneyShort(t.luong)}</td>
            <td class="pr-num">{moneyShort(t.phu_cap)}</td>
            <td class="pr-num">{moneyShort(t.ung)}</td>
            <td class="pr-num pr-net-td">{moneyShort(t.thuc_lanh)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function PayrollCard({ r, ym, toggleType, toggleWeekly,
  openUng, onToggleUng, advances, openPc, onTogglePc, allowances, apply, setAdvs, setAllows }: {
  r: PayrollRow; ym: string;
  toggleType: (r: PayrollRow) => void; toggleWeekly: (r: PayrollRow) => void;
  openUng: boolean; onToggleUng: () => void; advances?: SalaryAdvance[];
  openPc: boolean; onTogglePc: () => void; allowances?: SalaryAllowance[];
  apply: (d: PayrollMonth) => void;
  setAdvs: (f: (m: Record<number, SalaryAdvance[]>) => Record<number, SalaryAdvance[]>) => void;
  setAllows: (f: (m: Record<number, SalaryAllowance[]>) => Record<number, SalaryAllowance[]>) => void;
}) {
  const isTime = r.wage_type === "time";
  const wid = r.worker_id;

  const addAllow = async (a: number, note: string) => {
    try { apply(await addPayrollAllowance(ym, wid, a, note)); const l = await listPayrollAllowances(ym, wid); setAllows((m) => ({ ...m, [wid]: l })); }
    catch (e: any) { toast(e?.message || "Lỗi thêm phụ cấp", "err"); }
  };
  const voidAllow = async (id: number) => {
    const reason = await promptDialog("Lý do vô hiệu khoản phụ cấp này?", { placeholder: "VD: ghi nhầm số tiền…", okLabel: "Vô hiệu" });
    if (reason === null) return;
    if (!reason.trim()) { toast("Phải nhập lý do vô hiệu", "err"); return; }
    try { apply(await voidPayrollAllowance(ym, id, reason.trim())); const l = await listPayrollAllowances(ym, wid); setAllows((m) => ({ ...m, [wid]: l })); }
    catch (e: any) { toast(e?.message || "Lỗi vô hiệu", "err"); }
  };
  const addAdv = async (a: number, note: string, date: string) => {
    try { apply(await addPayrollAdvance(ym, wid, a, date, note)); const l = await listPayrollAdvances(ym, wid); setAdvs((m) => ({ ...m, [wid]: l })); }
    catch (e: any) { toast(e?.message || "Lỗi thêm ứng", "err"); }
  };
  const voidAdv = async (id: number) => {
    const reason = await promptDialog("Lý do vô hiệu lần ứng này?", { placeholder: "VD: ghi nhầm số tiền…", okLabel: "Vô hiệu" });
    if (reason === null) return;
    if (!reason.trim()) { toast("Phải nhập lý do vô hiệu", "err"); return; }
    try { apply(await voidPayrollAdvance(ym, id, reason.trim())); const l = await listPayrollAdvances(ym, wid); setAdvs((m) => ({ ...m, [wid]: l })); }
    catch (e: any) { toast(e?.message || "Lỗi vô hiệu", "err"); }
  };

  return (
    <section class="card pr-card">
      <div class="pr-top">
        <div class="pr-person">
          <span class="pr-avatar large">{initials(r.name)}</span>
          <div>
            <a class="pr-name-link" href={`#/sx-tho/${encodeURIComponent(r.name)}`}>{r.name}</a>
            <span class="pr-person-sub">{isTime ? "Lương thời gian" : "Lương sản phẩm"}</span>
          </div>
        </div>
        <div class="pr-card-net"><span>Thực lãnh</span><b class={r.thuc_lanh < 0 ? "t-danger" : ""}>{money(r.thuc_lanh)}</b></div>
      </div>

      <div class="pr-card-metrics">
        <div class="pr-card-metric"><span>Lương</span><b>{isTime ? "0" : money(r.luong)}</b></div>
        <div class="pr-card-metric"><span>Phụ cấp</span><a href={`#/nhap-phu-cap?ym=${encodeURIComponent(ym)}&worker_id=${wid}`}>{money(r.phu_cap)}</a></div>
        <div class="pr-card-metric advance"><span>Đã ứng</span><a href={`#/nhap-ung?ym=${encodeURIComponent(ym)}&worker_id=${wid}`}>{money(r.ung)}</a></div>
      </div>

      <div class="pr-card-tools">
        <button class={isTime ? "chip pr-type time" : "chip pr-type"} onClick={() => toggleType(r)}
          title="Bấm để đổi loại lương">{isTime ? "Thời gian" : "Sản phẩm"}</button>
        <label class="pr-weekly-control">
          <span>Nhận tuần {r.weekly && r.ung_weekly > 0 ? `· ${money(r.ung_weekly)}` : ""}</span>
          <span class={r.weekly ? "tgl on" : "tgl"} role="switch" aria-checked={r.weekly}
            onClick={() => toggleWeekly(r)}><span class="tgl-knob" /></span>
        </label>
      </div>
      <div class="pr-adv-toggle">
        <span>Chi tiết phụ cấp {r.pc_count ? <span class="muted small">· {r.pc_count} khoản</span> : null}</span>
        <button class="pr-toggle-btn" onClick={onTogglePc} aria-label={openPc ? "Đóng chi tiết phụ cấp" : "Mở chi tiết phụ cấp"}>{openPc ? "▾" : "▸"}</button>
      </div>
      {openPc && <EntryPanel entries={allowances} addPlaceholder="Số tiền phụ cấp"
        onAdd={(a, note) => addAllow(a, note)} onDel={voidAllow} />}
      <div class="pr-adv-toggle">
        <span>Chi tiết ứng lương {r.adv_count ? <span class="muted small">· {r.adv_count} lần nhập tay</span> : null}</span>
        <button class="pr-toggle-btn" onClick={onToggleUng} aria-label={openUng ? "Đóng chi tiết ứng lương" : "Mở chi tiết ứng lương"}>{openUng ? "▾" : "▸"}</button>
      </div>
      {openUng && <EntryPanel entries={advances} showDate addPlaceholder="Số tiền ứng"
        onAdd={(a, note, date) => addAdv(a, note, date)} onDel={voidAdv}
        extra={r.weekly && r.ung_weekly > 0 ? (
          <div class="pr-adv-row pr-adv-weekly">
            <span class="muted small">Lương tuần</span><b>{money(r.ung_weekly)}</b>
            <span class="muted small pr-adv-note">tự động = lương SP</span>
          </div>
        ) : null} />}
    </section>
  );
}
