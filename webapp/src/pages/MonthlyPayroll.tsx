// BẢNG LƯƠNG THÁNG (#/luong-thang) — CHỈ văn phòng. Mỗi thợ: loại lương (SP/thời gian),
// lương (SP tự tính; thời gian = 0 chờ chấm công), nhận lương tuần (theo tháng),
// PHỤ CẤP nhiều khoản, ỨNG lương nhiều lần → thực lãnh. Phụ cấp + ứng quản lý giống
// nhau (panel thêm/VÔ HIỆU khoản — không xoá, dòng giữ lại kèm ai/lúc nào/lý do).
// API: getMonthlyPayroll + payroll allowance/advance.
// MỌI Ô SỐ bấm được → popup xem/thao tác đúng ô (detail/PayrollCellPopup:
// Công/TC = chấm công từng ngày, L.công/L.TC/Lương/Lãnh = diễn giải công thức,
// P.cấp/Ứng = thêm/vô hiệu khoản tại chỗ). EntryPanel chuyển sang file popup.
// Ô TÊN thì KHÁC: mở TRANG riêng #/luong-thang/:worker_id (pages/PayrollWorker.tsx =
// hồ sơ lương tháng đầy đủ) — trước là popup, nội dung dài nên tách trang.
// (Cột THƯỞNG bỏ 2026-07-19 — phụ cấp nhiều khoản có nhãn đã thay thế; backend giữ
// field thuong cho tương thích, compute vẫn cộng nếu tháng cũ có dữ liệu.)
import { useEffect, useRef, useState } from "preact/hooks";
import {
  addPayrollAdvance, addPayrollAllowance, getMonthlyPayroll, isOffice,
  listPayrollAdvances, listPayrollAllowances, setPayrollAdvanceNote,
  setPayrollAllowanceNote, soVN, voidPayrollAdvance, voidPayrollAllowance,
  type PayrollMonth, type PayrollRow, type SalaryAdvance, type SalaryAllowance,
} from "../api";
import { moneyR as money, curYM, shiftYM, ymLabel } from "../format";
import { EntryPanel, PayrollCellPopup, type PayrollCol } from "../detail/PayrollCellPopup";
import { payrollActions } from "../detail/payrollActions";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { toast, promptDialog } from "../ui/feedback";

const congVN = (n: number) => String(Math.round(n * 100) / 100).replace(".", ",");
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
  // Popup ô bảng: {wid, col} — row truyền vào popup tra TƯƠI từ data mỗi render
  const [pop, setPop] = useState<{ wid: number; col: PayrollCol } | null>(null);

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
  // 3 thao tác hồ sơ lương dùng CHUNG với trang #/luong-thang/:id (detail/payrollActions)
  const { toggleType, editMoc, toggleWeekly } = payrollActions(ym, apply, load);
  // Ô TÊN → TRANG lương của thợ (trước là popup; nội dung dài nên tách trang riêng)
  const openWorker = (wid: number) => { window.location.hash = `#/luong-thang/${wid}?ym=${encodeURIComponent(ym)}`; };

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
              <PayrollTable data={data} toggleType={toggleType} toggleWeekly={toggleWeekly} editMoc={editMoc}
                onCell={(wid, col) => setPop({ wid, col })} onName={openWorker} />
            ) : (
              <div class="pr-card-grid">
                {data.workers.map((r) => (
                  <PayrollCard key={r.worker_id} r={r} ym={ym}
                    toggleType={toggleType} toggleWeekly={toggleWeekly} editMoc={editMoc}
                    openUng={openUng === r.worker_id} onToggleUng={() => toggleUng(r.worker_id)} advances={advs[r.worker_id]}
                    openPc={openPc === r.worker_id} onTogglePc={() => togglePc(r.worker_id)} allowances={allows[r.worker_id]}
                    apply={apply} setAdvs={setAdvs} setAllows={setAllows} />
                ))}
              </div>
            )}
          </>
        )}
      {pop && data && (() => {
        const r = data.workers.find((w) => w.worker_id === pop.wid);
        return r ? (
          <PayrollCellPopup ym={ym} r={r} col={pop.col}
            onClose={() => setPop(null)} onCol={(col) => setPop({ wid: pop.wid, col })}
            apply={apply} editMoc={editMoc} />
        ) : null;
      })()}
    </div>
  );
}

function PayrollTable({ data, toggleType, toggleWeekly, editMoc, onCell, onName }: {
  data: PayrollMonth;
  toggleType: (r: PayrollRow) => void; toggleWeekly: (r: PayrollRow) => void;
  editMoc: (r: PayrollRow) => void;
  onCell: (wid: number, col: PayrollCol) => void;
  onName: (wid: number) => void;   // ô TÊN → trang lương của thợ
}) {
  const t = data.totals;
  // SỐ ĐẦY ĐỦ (không rút gọn) → bảng RỘNG hơn màn: thân cuộn NGANG, cột Thợ ghim
  // trái; header tách thanh sticky top (dưới app-bar) + scrollLeft đồng bộ từ thân
  // — cùng kỹ thuật lưới chấm công.
  // ⚠ 2 BẢNG THẲNG CỘT chỉ đúng khi table-layout:fixed THẬT ĂN → bảng phải có bề
  // rộng XÁC ĐỊNH (`width:100%` + min-width dưới đây). Trước đây dùng
  // `width:max-content` → Chrome phải đo bằng auto-layout, colgroup mất tác dụng,
  // mỗi bảng tự co theo nội dung CỦA NÓ (header nhãn ngắn ≠ thân số dài) → lệch tới
  // ~180px, đổi liên tục khi resize. Đừng đưa max-content/width:auto trở lại.
  // Bề rộng theo EM (không px) để mobile font nhỏ hơn thì bảng tự hẹp lại; số đo
  // thực: dòng TỔNG ~9 chữ số cần ≤8,3em, chip Loại/toggle Tuần cần ≥5,4em/5,7em,
  // tên thợ dài cắt bằng ellipsis. Mốc (8,6) + Lương (8,8) rộng hơn phần còn lại vì
  // còn đeo dấu ↩ (mốc kế thừa) / ⁺ (lương đã gộp phụ cấp phiếu) — đo bằng Playwright,
  // hụt là chữ bị cắt ngay.
  const COL_EM = [12, 5.5, 5.9, 8.6, 5.4, 8.4, 5.4, 8.4, 8.8, 8.4, 8.4, 8.4];
  const totalEm = COL_EM.reduce((a, b) => a + b, 0);
  const tableStyle = `min-width:${totalEm}em`;
  const headRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  // Resize cửa sổ → thân bị CLAMP scrollLeft (bảng vừa màn thì về 0) mà header
  // không hay biết vì chỉ sync trong onScroll → lệch. Bám ResizeObserver để sync lại.
  useEffect(() => {
    const head = headRef.current, body = bodyRef.current;
    if (!head || !body) return;
    const sync = () => { head.scrollLeft = body.scrollLeft; };
    const ro = new ResizeObserver(sync);
    ro.observe(body);
    window.addEventListener("resize", sync);
    return () => { ro.disconnect(); window.removeEventListener("resize", sync); };
  }, []);
  const cols = <colgroup>{COL_EM.map((w, i) => <col key={i} style={`width:${w}em`} />)}</colgroup>;
  return (
    <div class="pr-table-wrap">
      <div class="pr-thead-bar" ref={headRef}>
        <table class="pr-table" style={tableStyle}>
          {cols}
          <thead>
            <tr>
              <th class="pr-sticky">Thợ</th><th>Loại</th><th>Tuần</th><th>Mốc</th><th>Công</th>
              <th title="Lương theo ngày công">L.công</th><th title="Giờ tăng ca">TC</th>
              <th title="Lương tăng ca ×1,2">L.TC</th>
              <th>Lương</th><th>P.cấp</th><th>Ứng</th><th>Lãnh</th>
            </tr>
          </thead>
        </table>
      </div>
      <div class="pr-tbody-scroll" ref={bodyRef}
        onScroll={() => { if (headRef.current && bodyRef.current) headRef.current.scrollLeft = bodyRef.current.scrollLeft; }}>
        <table class="pr-table" style={tableStyle}>
          {cols}
          <tbody>
          {data.workers.map((r) => {
            const isTime = r.wage_type === "time";
            // Ô số bấm được → popup xem/thao tác đúng cột (PayrollCellPopup)
            const tap = (col: PayrollCol) => ({
              role: "button" as const, tabIndex: 0, onClick: () => onCell(r.worker_id, col),
              onKeyDown: (e: any) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onCell(r.worker_id, col); } },
            });
            return (
              <tr key={r.worker_id}>
                <td class="pr-sticky pr-td-name pr-td-tap" role="button" tabIndex={0}
                  title="Mở trang lương tháng của thợ"
                  onClick={() => onName(r.worker_id)}
                  onKeyDown={(e: any) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onName(r.worker_id); } }}>
                  {/* Dưới tên = TỔNG TIỀN NHẬN ĐƯỢC của tháng (lương + phụ cấp + thưởng),
                      CHƯA trừ ứng — cố ý KHÁC cột Lãnh (thực lãnh = đã trừ ứng). Cột Thợ
                      ghim trái nên thấy ngay số này khỏi phải cuộn ngang. */}
                  <span class="pr-worker">
                    <span class="pr-avatar">{initials(r.name)}</span>
                    <span class="pr-worker-main">
                      <span class="pr-worker-nm">{r.name}</span>
                      <span class="pr-worker-net"
                        title={`Tổng tiền lương ${ymLabel(data.ym).toLowerCase()} = lương + phụ cấp (chưa trừ ứng)`}>
                        {money(r.luong + r.phu_cap + r.thuong)}
                      </span>
                    </span>
                  </span>
                </td>
                <td class="pr-td-mid">
                  <button class={isTime ? "chip pr-type time" : "chip pr-type"} onClick={() => toggleType(r)}
                    title="Bấm để đổi loại lương">{isTime ? "TG" : "SP"}</button>
                </td>
                <td class="pr-td-mid">
                  <span class={r.weekly ? "tgl on" : "tgl"} role="switch" aria-checked={r.weekly}
                    onClick={() => toggleWeekly(r)} style="cursor:pointer" title="Nhận lương tuần"><span class="tgl-knob" /></span>
                </td>
                {/* Mốc = mốc lương THÁNG ĐANG XEM (lưu theo từng tháng). Dấu ↩ = tháng
                    này không đặt riêng, đang kế thừa mốc đặt ở tháng trước đó. Bấm ô
                    mở popup: sửa mốc + TRAO ĐỔI về mốc lương của thợ (mọi tháng). */}
                {isTime ? (
                  <td class="pr-num pr-td-tap" title={`Mốc lương tháng — ${r.moc_own ? "đặt riêng tháng này" : r.moc_ym ? `kế thừa mốc đặt ở tháng ${r.moc_ym}` : "mốc hồ sơ thợ"}. Bấm để sửa / trao đổi`} {...tap("moc")}>
                    <span class="pr-ung-btn">
                      {r.monthly_salary ? money(r.monthly_salary) : "đặt…"}
                      {r.monthly_salary && !r.moc_own ? <sup title="kế thừa từ tháng trước"> ↩</sup> : null}
                    </span>
                  </td>
                ) : <td class="pr-num is-zero">—</td>}
                <td class={`pr-td-tap ${r.cong > 0 ? "pr-num" : "pr-num is-zero"}`} title="Ngày công từ máy chấm — bấm xem từng ngày" {...tap("cong")}>
                  {r.cong > 0 ? congVN(r.cong) : "—"}
                </td>
                <td class={`pr-td-tap ${isTime && r.luong_cong ? "pr-num" : "pr-num is-zero"}`} title="Lương theo ngày công = mốc/26 × công — bấm xem cách tính" {...tap("luong_cong")}>
                  {isTime ? money(r.luong_cong) : "—"}
                </td>
                <td class={`pr-td-tap ${r.ot_gio > 0 ? "pr-num" : "pr-num is-zero"}`} title="Số giờ tăng ca — bấm xem từng ngày" {...tap("tc")}>
                  {r.ot_gio > 0 ? congVN(r.ot_gio) : "—"}
                </td>
                <td class={`pr-td-tap ${isTime && r.luong_tc ? "pr-num" : "pr-num is-zero"}`} title="Lương tăng ca ×1,2 — bấm xem cách tính" {...tap("luong_tc")}>
                  {isTime ? money(r.luong_tc) : "—"}
                </td>
                {/* Lương thợ SP ĐÃ GỒM phụ cấp ghi trong phiếu SX (cột P.cấp là phụ cấp
                    THÁNG, khác hẳn) → nói trong tooltip + dấu ⁺ cho khỏi tưởng bỏ sót */}
                <td class={`pr-td-tap ${!r.luong ? "pr-num is-zero" : "pr-num"}`} {...tap("luong")}
                  title={r.pc_phieu ? `Gồm ${money(r.pc_phieu)}đ phụ cấp ghi trong phiếu SX — bấm xem cách tính`
                                    : "Bấm xem cách tính lương"}>
                  {money(r.luong)}{r.pc_phieu ? <sup title="đã gộp phụ cấp phiếu SX"> ⁺</sup> : null}
                </td>
                <td class="pr-num pr-td-tap" title="Phụ cấp — bấm thêm/vô hiệu khoản" {...tap("pc")}>
                  <span class="pr-ung-btn">{money(r.phu_cap)}{r.pc_count ? <sup> {r.pc_count}</sup> : null}</span>
                </td>
                <td class="pr-num pr-td-tap" title="Ứng lương — bấm thêm/vô hiệu lần ứng" {...tap("ung")}>
                  <span class="pr-ung-btn">{money(r.ung)}{r.adv_count ? <sup> {r.adv_count}</sup> : null}</span>
                </td>
                <td class={`pr-td-tap ${r.thuc_lanh < 0 ? "pr-num pr-net-td t-danger" : "pr-num pr-net-td"}`} title="Bấm xem diễn giải thực lãnh" {...tap("net")}>{money(r.thuc_lanh)}</td>
              </tr>
            );
          })}
          </tbody>
          <tfoot>
            <tr>
              <td class="pr-sticky pr-td-name">
                <span class="pr-worker-main">
                  <span class="pr-worker-nm">Tổng</span>
                  <span class="pr-worker-net" title="Tổng tiền lương cả xưởng (lương + phụ cấp, chưa trừ ứng)">
                    {money(t.luong + t.phu_cap + t.thuong)}
                  </span>
                </span>
              </td><td></td><td></td><td></td>
              <td class="pr-num">{congVN(data.workers.reduce((a, r) => a + (r.cong || 0), 0))}</td>
              <td class="pr-num">{money(data.workers.reduce((a, r) => a + (r.luong_cong || 0), 0))}</td>
              <td class="pr-num">{congVN(data.workers.reduce((a, r) => a + (r.ot_gio || 0), 0))}</td>
              <td class="pr-num">{money(data.workers.reduce((a, r) => a + (r.luong_tc || 0), 0))}</td>
              <td class="pr-num">{money(t.luong)}</td>
              <td class="pr-num">{money(t.phu_cap)}</td>
              <td class="pr-num">{money(t.ung)}</td>
              <td class="pr-num pr-net-td">{money(t.thuc_lanh)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

function PayrollCard({ r, ym, toggleType, toggleWeekly, editMoc,
  openUng, onToggleUng, advances, openPc, onTogglePc, allowances, apply, setAdvs, setAllows }: {
  r: PayrollRow; ym: string;
  toggleType: (r: PayrollRow) => void; toggleWeekly: (r: PayrollRow) => void;
  editMoc: (r: PayrollRow) => void;
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
  // ✏️ sửa ghi chú khoản đã ghi — SỐ TIỀN bất biến (sai tiền thì vô hiệu rồi ghi lại)
  const askNote = async (title: string, cur: string) => {
    const next = await promptDialog(title, { initial: cur, placeholder: "VD: ăn trưa, xăng xe…", okLabel: "Lưu" });
    return next === null || next.trim() === cur ? null : next.trim();
  };
  const noteAllow = async (id: number, cur: string) => {
    const next = await askNote("Nội dung khoản phụ cấp", cur);
    if (next === null) return;
    try { apply(await setPayrollAllowanceNote(ym, id, next)); const l = await listPayrollAllowances(ym, wid); setAllows((m) => ({ ...m, [wid]: l })); toast("Đã lưu nội dung", "ok"); }
    catch (e: any) { toast(e?.message || "Lỗi lưu nội dung", "err"); }
  };
  const noteAdv = async (id: number, cur: string) => {
    const next = await askNote("Ghi chú lần ứng", cur);
    if (next === null) return;
    try { apply(await setPayrollAdvanceNote(ym, id, next)); const l = await listPayrollAdvances(ym, wid); setAdvs((m) => ({ ...m, [wid]: l })); toast("Đã lưu ghi chú", "ok"); }
    catch (e: any) { toast(e?.message || "Lỗi lưu ghi chú", "err"); }
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
            <a class="pr-name-link" href={`#/luong-thang/${wid}?ym=${encodeURIComponent(ym)}`}>{r.name}</a>
            <span class="pr-person-sub">{isTime ? "Lương thời gian" : "Lương sản phẩm"}</span>
          </div>
        </div>
        <div class="pr-card-net"><span>Thực lãnh</span><b class={r.thuc_lanh < 0 ? "t-danger" : ""}>{money(r.thuc_lanh)}</b></div>
      </div>

      <div class="pr-card-metrics">
        <div class="pr-card-metric"><span>Lương</span><b>{money(r.luong)}</b></div>
        <div class="pr-card-metric"><span>Phụ cấp</span><a href={`#/nhap-phu-cap?ym=${encodeURIComponent(ym)}&worker_id=${wid}`}>{money(r.phu_cap)}</a></div>
        <div class="pr-card-metric advance"><span>Đã ứng</span><a href={`#/nhap-ung?ym=${encodeURIComponent(ym)}&worker_id=${wid}`}>{money(r.ung)}</a></div>
      </div>

      {isTime && (
        <div class="pr-moc-row">
          <button class="pr-ung-btn" onClick={() => editMoc(r)}
            title={`Mốc của tháng đang xem — ${r.moc_own ? "đặt riêng tháng này" : r.moc_ym ? `kế thừa mốc đặt ở tháng ${r.moc_ym}` : "mốc hồ sơ thợ"}. Bấm để sửa`}>
            Mốc {r.monthly_salary ? money(r.monthly_salary) : "chưa đặt — bấm sửa"}
            {r.monthly_salary && !r.moc_own ? " ↩" : ""}
          </button>
          <span class="muted small">
            {r.cong} công = {money(r.luong_cong)}đ · TC {r.ot_gio}g = {money(r.luong_tc)}đ (×1,2)
            {" "}<a href={`#/cham-cong/${wid}?ym=${encodeURIComponent(ym)}`}>→ chấm công</a>
          </span>
        </div>
      )}
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
        onAdd={(a, note) => addAllow(a, note)} onDel={voidAllow} onNote={noteAllow} />}
      <div class="pr-adv-toggle">
        <span>Chi tiết ứng lương {r.adv_count ? <span class="muted small">· {r.adv_count} lần nhập tay</span> : null}</span>
        <button class="pr-toggle-btn" onClick={onToggleUng} aria-label={openUng ? "Đóng chi tiết ứng lương" : "Mở chi tiết ứng lương"}>{openUng ? "▾" : "▸"}</button>
      </div>
      {openUng && <EntryPanel entries={advances} showDate addPlaceholder="Số tiền ứng"
        onAdd={(a, note, date) => addAdv(a, note, date)} onDel={voidAdv} onNote={noteAdv}
        extra={r.weekly && r.ung_weekly > 0 ? (
          <div class="pr-adv-row pr-adv-weekly">
            <span class="muted small">Lương tuần</span><b>{money(r.ung_weekly)}</b>
            <span class="muted small pr-adv-note">tự động = lương SP</span>
          </div>
        ) : null} />}
    </section>
  );
}
