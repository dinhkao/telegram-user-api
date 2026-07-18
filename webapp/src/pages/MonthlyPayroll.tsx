// BẢNG LƯƠNG THÁNG (#/luong-thang) — CHỈ văn phòng. Mỗi thợ: loại lương (SP/thời gian),
// lương (SP tự tính; thời gian = 0 chờ chấm công), nhận lương tuần (theo tháng),
// PHỤ CẤP nhiều khoản, THƯỞNG, ỨNG lương nhiều lần → thực lãnh. Phụ cấp + ứng quản lý
// giống nhau (panel thêm/xoá khoản). API: getMonthlyPayroll + payroll allowance/advance.
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import {
  addPayrollAdvance, addPayrollAllowance, deletePayrollAdvance, deletePayrollAllowance,
  getMonthlyPayroll, isOffice, listPayrollAdvances, listPayrollAllowances, setPayrollAdjust,
  soVN, updateWorker, type PayrollMonth, type PayrollRow, type SalaryAdvance, type SalaryAllowance,
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
const initials = (name: string) => name.trim().split(/\s+/).slice(-2).map((part) => part[0] || "").join("").toUpperCase();

// Ghi nhớ theo PHIÊN (module scope, reset khi tải lại trang): THÁNG đang xem +
// vị trí CUỘN bảng (theo tháng, cả dọc lẫn ngang). Kiểu hiển thị lưu localStorage
// (mặc định BẢNG). → quay lại trang (back) giữ nguyên tháng + chỗ đang cuộn.
const VIEW_KEY = "payroll_view";
let _savedYm: string | null = null;
const _tblScroll: Record<string, { top: number; left: number }> = {};
const loadView = (): "table" | "card" => {
  try { return localStorage.getItem(VIEW_KEY) === "card" ? "card" : "table"; } catch { return "table"; }
};

export function MonthlyPayroll() {
  const [ym, setYm] = useState(() => _savedYm || curYM());
  const [data, setData] = useState<PayrollMonth | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [view, setViewState] = useState<"table" | "card">(loadView);
  const setView = (v: "table" | "card") => { setViewState(v); try { localStorage.setItem(VIEW_KEY, v); } catch { /**/ } };
  const [openUng, setOpenUng] = useState<number | null>(null);
  const [openPc, setOpenPc] = useState<number | null>(null);
  const [advs, setAdvs] = useState<Record<number, SalaryAdvance[]>>({});
  const [allows, setAllows] = useState<Record<number, SalaryAllowance[]>>({});

  const load = () => {
    setLoading(true);
    getMonthlyPayroll(ym)
      .then((d) => { setData(d); setErr(""); setDraft({}); })
      .catch((e: any) => setErr(e?.message || "Lỗi tải bảng lương"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, [ym]);
  useEffect(() => { _savedYm = ym; }, [ym]);   // nhớ tháng đang xem cho lần quay lại

  const apply = (d: PayrollMonth) => { setData(d); setDraft({}); };

  const saveThuong = async (wid: number, val: string) => {
    try { apply(await setPayrollAdjust(ym, wid, { thuong: num(val) })); }
    catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); }
  };
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
      sub="lương SP tự tính + phụ cấp/thưởng/ứng theo tháng" />
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
                  <div class="pr-stat bonus"><span>Thưởng</span><b>+{money(totals.thuong)}</b></div>
                  <a class="pr-stat advance" href={`#/nhap-ung?ym=${encodeURIComponent(ym)}`}><span>Đã ứng</span><b>−{money(totals.ung)}</b></a>
                </div>
              </section>
            )}
            {view === "table" ? (
              <PayrollTable data={data} draft={draft} setDraft={setDraft}
                saveThuong={saveThuong} toggleType={toggleType} toggleWeekly={toggleWeekly} />
            ) : (
              <div class="pr-card-grid">
                {data.workers.map((r) => (
                  <PayrollCard key={r.worker_id} r={r} ym={ym} draft={draft} setDraft={setDraft}
                    saveThuong={saveThuong} toggleType={toggleType} toggleWeekly={toggleWeekly}
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

// Panel liệt kê + thêm/xoá KHOẢN (dùng cho cả phụ cấp lẫn ứng). extra = dòng đọc-thêm ở đầu.
function EntryPanel({ entries, showDate, addPlaceholder, onAdd, onDel, extra }: {
  entries?: { id: number; amount: number; note: string; adv_date?: string }[];
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
        <div class="pr-adv-row" key={e.id}>
          {showDate ? <span class="muted small">{e.adv_date || "—"}</span> : null}
          <b>{money(e.amount)}</b>
          <span class="muted small pr-adv-note">{e.note}</span>
          <button class="pr-adv-del" onClick={() => onDel(e.id)} aria-label="Xoá">✕</button>
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

function PayrollTable({ data, draft, setDraft, saveThuong, toggleType, toggleWeekly }: {
  data: PayrollMonth; draft: Record<string, string>;
  setDraft: (f: (d: Record<string, string>) => Record<string, string>) => void;
  saveThuong: (wid: number, val: string) => void;
  toggleType: (r: PayrollRow) => void; toggleWeekly: (r: PayrollRow) => void;
}) {
  const t = data.totals;
  const wrapRef = useRef<HTMLDivElement>(null);
  const floatRef = useRef<HTMLDivElement>(null);
  const headerRow = () => (
    <tr>
      <th class="pr-sticky">Thợ</th><th>Loại</th><th>Tuần</th><th>Lương</th>
      <th>Phụ cấp</th><th>Thưởng</th><th>Ứng</th><th>Thực lãnh</th>
    </tr>
  );

  // Khôi phục vị trí cuộn NGANG (tháng này) khi vào/quay lại; cuộn DỌC do window (useScrollMemory) lo.
  useLayoutEffect(() => {
    const el = wrapRef.current; if (!el) return;
    const s = _tblScroll[data.ym];
    if (s) el.scrollLeft = s.left;
  }, [data.ym]);

  // HEADER NỔI: khi header thật cuộn qua đỉnh, hiện bản sao position:fixed ngay dưới
  // app-bar; đồng bộ cuộn NGANG (+ giữ cột Thợ đóng băng bằng counter-translate).
  useEffect(() => {
    const wrap = wrapRef.current, float = floatRef.current;
    if (!wrap || !float) return;
    const ftable = float.querySelector("table") as HTMLTableElement | null;
    const realThead = wrap.querySelector("thead") as HTMLElement | null;
    if (!ftable || !realThead) return;
    const bar = document.querySelector(".app-bar");
    const topPx = bar ? Math.round(bar.getBoundingClientRect().height) : 0;

    const syncWidths = () => {
      const rths = realThead.querySelectorAll("th");
      const fths = ftable.querySelectorAll("th");
      let total = 0;
      rths.forEach((th, i) => {
        const w = (th as HTMLElement).getBoundingClientRect().width;
        total += w;
        const f = fths[i] as HTMLElement | undefined;
        if (f) f.style.width = f.style.minWidth = f.style.maxWidth = `${w}px`;
      });
      ftable.style.width = `${total}px`;
    };
    const syncX = () => {
      const sl = wrap.scrollLeft;
      ftable.style.transform = `translateX(${-sl}px)`;
      const f = ftable.querySelector("th") as HTMLElement | null;
      if (f) f.style.transform = `translateX(${sl}px)`;   // cột Thợ đứng yên khi cuộn ngang
    };
    const update = () => {
      const r = wrap.getBoundingClientRect();
      const on = r.top < topPx && r.bottom > topPx + 24;  // header thật đã cuộn lên + bảng còn trong tầm
      if (!on) { if (float.style.display !== "none") float.style.display = "none"; return; }
      if (float.style.display !== "block") { float.style.display = "block"; syncWidths(); }
      float.style.top = `${topPx}px`;
      float.style.left = `${r.left}px`;
      float.style.width = `${r.width}px`;
      syncX();
    };

    update();
    const onScroll = () => update();
    const onWrapScroll = () => { if (float.style.display === "block") syncX(); };
    window.addEventListener("scroll", onScroll, { passive: true });
    wrap.addEventListener("scroll", onWrapScroll, { passive: true });
    const ro = new ResizeObserver(() => { syncWidths(); update(); });
    ro.observe(wrap);
    return () => {
      window.removeEventListener("scroll", onScroll);
      wrap.removeEventListener("scroll", onWrapScroll);
      ro.disconnect();
    };
  }, [data]);

  return (
    <>
      <div class="pr-thead-float" ref={floatRef} aria-hidden="true">
        <table class="pr-table"><thead>{headerRow()}</thead></table>
      </div>
      <div class="pr-table-wrap" ref={wrapRef}
        onScroll={(e: any) => { _tblScroll[data.ym] = { top: 0, left: e.currentTarget.scrollLeft }; }}>
        <table class="pr-table">
          <thead>{headerRow()}</thead>
        <tbody>
          {data.workers.map((r) => {
            const isTime = r.wage_type === "time";
            const kTh = `${r.worker_id}:thuong`;
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
                <td class={isTime || !r.luong ? "pr-num is-zero" : "pr-num"}>{isTime ? "0" : money(r.luong)}</td>
                <td class="pr-num">
                  <a class="pr-ung-btn" href={`#/nhap-phu-cap?ym=${encodeURIComponent(data.ym)}&worker_id=${r.worker_id}`} title="Mở phụ cấp của nhân viên">
                    {money(r.phu_cap)}{r.pc_count ? <sup> {r.pc_count}</sup> : null}
                  </a>
                </td>
                <td class="pr-td-in">
                  <input class="pw-input pr-tin" inputMode="numeric" placeholder="0"
                    value={draft[kTh] !== undefined ? draft[kTh] : (r.thuong ? String(r.thuong) : "")}
                    onInput={(e: any) => setDraft((d) => ({ ...d, [kTh]: e.target.value }))}
                    onBlur={(e: any) => saveThuong(r.worker_id, e.target.value)}
                    onKeyDown={(e: any) => { if (e.key === "Enter") e.target.blur(); }} />
                </td>
                <td class="pr-num">
                  <a class="pr-ung-btn" href={`#/nhap-ung?ym=${encodeURIComponent(data.ym)}&worker_id=${r.worker_id}`} title="Mở ứng lương của nhân viên">
                    {money(r.ung)}{r.adv_count ? <sup> {r.adv_count}</sup> : null}
                  </a>
                </td>
                <td class={r.thuc_lanh < 0 ? "pr-num pr-net-td t-danger" : "pr-num pr-net-td"}>{money(r.thuc_lanh)}</td>
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
    </>
  );
}

function PayrollCard({ r, ym, draft, setDraft, saveThuong, toggleType, toggleWeekly,
  openUng, onToggleUng, advances, openPc, onTogglePc, allowances, apply, setAdvs, setAllows }: {
  r: PayrollRow; ym: string; draft: Record<string, string>;
  setDraft: (f: (d: Record<string, string>) => Record<string, string>) => void;
  saveThuong: (wid: number, val: string) => void;
  toggleType: (r: PayrollRow) => void; toggleWeekly: (r: PayrollRow) => void;
  openUng: boolean; onToggleUng: () => void; advances?: SalaryAdvance[];
  openPc: boolean; onTogglePc: () => void; allowances?: SalaryAllowance[];
  apply: (d: PayrollMonth) => void;
  setAdvs: (f: (m: Record<number, SalaryAdvance[]>) => Record<number, SalaryAdvance[]>) => void;
  setAllows: (f: (m: Record<number, SalaryAllowance[]>) => Record<number, SalaryAllowance[]>) => void;
}) {
  const kTh = `${r.worker_id}:thuong`;
  const isTime = r.wage_type === "time";
  const wid = r.worker_id;

  const addAllow = async (a: number, note: string) => {
    try { apply(await addPayrollAllowance(ym, wid, a, note)); const l = await listPayrollAllowances(ym, wid); setAllows((m) => ({ ...m, [wid]: l })); }
    catch (e: any) { toast(e?.message || "Lỗi thêm phụ cấp", "err"); }
  };
  const delAllow = async (id: number) => {
    if (!(await confirmDialog("Xoá khoản phụ cấp này?"))) return;
    try { apply(await deletePayrollAllowance(ym, id)); setAllows((m) => ({ ...m, [wid]: (m[wid] || []).filter((x) => x.id !== id) })); }
    catch (e: any) { toast(e?.message || "Lỗi xoá", "err"); }
  };
  const addAdv = async (a: number, note: string, date: string) => {
    try { apply(await addPayrollAdvance(ym, wid, a, date, note)); const l = await listPayrollAdvances(ym, wid); setAdvs((m) => ({ ...m, [wid]: l })); }
    catch (e: any) { toast(e?.message || "Lỗi thêm ứng", "err"); }
  };
  const delAdv = async (id: number) => {
    if (!(await confirmDialog("Xoá lần ứng này?"))) return;
    try { apply(await deletePayrollAdvance(ym, id)); setAdvs((m) => ({ ...m, [wid]: (m[wid] || []).filter((x) => x.id !== id) })); }
    catch (e: any) { toast(e?.message || "Lỗi xoá", "err"); }
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
        <label class="pr-card-metric editable"><span>Thưởng</span>
          <input class="pw-input" inputMode="numeric" placeholder="0"
            value={draft[kTh] !== undefined ? draft[kTh] : (r.thuong ? String(r.thuong) : "")}
            onInput={(e: any) => setDraft((d) => ({ ...d, [kTh]: e.target.value }))}
            onBlur={(e: any) => saveThuong(wid, e.target.value)}
            onKeyDown={(e: any) => { if (e.key === "Enter") e.target.blur(); }} />
        </label>
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
        onAdd={(a, note) => addAllow(a, note)} onDel={delAllow} />}
      <div class="pr-adv-toggle">
        <span>Chi tiết ứng lương {r.adv_count ? <span class="muted small">· {r.adv_count} lần nhập tay</span> : null}</span>
        <button class="pr-toggle-btn" onClick={onToggleUng} aria-label={openUng ? "Đóng chi tiết ứng lương" : "Mở chi tiết ứng lương"}>{openUng ? "▾" : "▸"}</button>
      </div>
      {openUng && <EntryPanel entries={advances} showDate addPlaceholder="Số tiền ứng"
        onAdd={(a, note, date) => addAdv(a, note, date)} onDel={delAdv}
        extra={r.weekly && r.ung_weekly > 0 ? (
          <div class="pr-adv-row pr-adv-weekly">
            <span class="muted small">Lương tuần</span><b>{money(r.ung_weekly)}</b>
            <span class="muted small pr-adv-note">tự động = lương SP</span>
          </div>
        ) : null} />}
    </section>
  );
}
