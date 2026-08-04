// BẢNG LƯƠNG THÁNG (#/luong-thang) — CHỈ văn phòng. Mỗi thợ: loại lương (SP/thời gian),
// lương (SP tự tính; thời gian = 0 chờ chấm công), nhận lương tuần (theo tháng),
// PHỤ CẤP nhiều khoản, ỨNG lương nhiều lần → thực lãnh. Phụ cấp + ứng quản lý giống
// nhau (panel thêm/VÔ HIỆU khoản — không xoá, dòng giữ lại kèm ai/lúc nào/lý do).
// API: getMonthlyPayroll + payroll allowance/advance.
// 2 NGUỒN LƯƠNG là 2 CỘT RIÊNG, không gộp: "Lương công+TC" (thợ lương thời gian =
// lương ngày công + lương tăng ca) và "Lương SP" (thợ lương sản phẩm). Mỗi thợ chỉ ăn
// 1 trong 2 nên cột kia là "—"; chi tiết công/TC vẫn xem trong popup của ô.
// TRỪ BHXH = cột riêng, số lưu theo TỪNG THÁNG + kế thừa như Mốc lương (đặt tháng nào
// áp từ tháng đó trở đi — salary_store/bhxh.py); đã trừ trong cột Lãnh.
// 2 cột THƯỞNG "Ch.cần" + "Vệ sinh" = NÚT BẬT/TẮT, bấm thẳng vào ô (chuyên cần cố
// định, vệ sinh = 12.000đ × ngày công — salary_store/bonus.py). KHÁC BHXH/Mốc:
// 2 cờ này KHÔNG kế thừa, bật tháng nào chỉ ăn tháng đó.
// MỌI Ô SỐ bấm được → popup xem/thao tác đúng ô (detail/PayrollCellPopup:
// Công/TC = chấm công từng ngày, 2 cột NGUỒN LƯƠNG + Lãnh = diễn giải công thức,
// P.cấp/Ứng = thêm/vô hiệu khoản tại chỗ qua detail/EntryPanel, BHXH = sửa mức trừ).
// Ô TÊN thì KHÁC: mở POPUP hồ sơ lương tháng đầy đủ ngay tại trang này
// (detail/PayrollWorkerPopup, nội dung dùng chung detail/PayrollWorkerSheet với
// trang riêng #/luong-thang/:worker_id — trang vẫn giữ để chia sẻ link).
// (Cột THƯỞNG bỏ 2026-07-19 — phụ cấp nhiều khoản có nhãn đã thay thế; backend giữ
// field thuong cho tương thích, compute vẫn cộng nếu tháng cũ có dữ liệu.)
// SẮP XẾP: bấm tiêu đề cột (luật + định nghĩa cột ở detail/payrollSort.ts) — áp cho
// CẢ view Bảng lẫn view Thẻ. View Thẻ = detail/PayrollCard.tsx (tách ra vì trần 400 dòng).
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import {
  getMonthlyPayroll, isOffice, listPayrollAdvances, listPayrollAllowances,
  type PayrollMonth, type PayrollRow, type SalaryAdvance, type SalaryAllowance,
} from "../api";
import { moneyR as money, curYM, shiftYM, ymLabel } from "../format";
import { PayrollCellPopup, type PayrollCol } from "../detail/PayrollCellPopup";
import { PayrollCard } from "../detail/PayrollCard";
import { PayrollWorkerPopup } from "../detail/PayrollWorkerPopup";
import { payrollActions } from "../detail/payrollActions";
import { COLS, loadSort, nextSort, saveSort, sortRows, type Sort } from "../detail/payrollSort";
import { isTimeWage, otInCong, wageChip, wageLabel } from "../detail/wageType";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { Loading, EmptyState, ErrorState } from "../ui/states";

const congVN = (n: number) => String(Math.round(n * 100) / 100).replace(".", ",");
// Gương của salary_store/bonus.THUONG_VE_SINH_MOI_NGAY — CHỈ dùng cho chú thích
// ("12.000đ × N công"); số tiền thật luôn do server tính, client không tự cộng.
const VS_MOI_NGAY = 12000;
/** TỔNG TIỀN NHẬN của 1 thợ trong tháng (CHƯA trừ ứng/BHXH) — phải gồm CẢ 2 khoản
 *  thưởng chuyên cần/vệ sinh, không thì bật/tắt thưởng mà số xanh dưới tên đứng im. */
const tongNhan = (r: PayrollRow) => r.luong + r.phu_cap + r.thuong + r.thuong_cc + r.thuong_vs;

/** Màn hẹp (cùng mốc 720px với media query bảng lương trong styles.css) — dùng để
 *  thu cột Thợ ghim trái, thứ CSS không đè được vì width nằm inline trên <col>. */
const NARROW_MQ = "(max-width: 720px)";
function useNarrow() {
  const [narrow, setNarrow] = useState(
    () => typeof window !== "undefined" && !!window.matchMedia?.(NARROW_MQ).matches);
  useEffect(() => {
    const mq = window.matchMedia?.(NARROW_MQ);
    if (!mq) return;
    const on = () => setNarrow(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return narrow;
}

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
  // Sắp xếp theo cột (null = thứ tự server). Nhớ trong localStorage; áp cả 2 view.
  const [sort, setSortState] = useState<Sort | null>(loadSort);
  const onSort = (key: any, num: boolean) => {
    const next = nextSort(sort, key, num);
    setSortState(next); saveSort(next);
  };
  const rows = useMemo(() => sortRows(data?.workers || [], sort), [data, sort]);

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
  // 4 thao tác hồ sơ lương dùng CHUNG với trang #/luong-thang/:id (detail/payrollActions)
  const { toggleType, editMoc, editBhxh, toggleWeekly, toggleThuongCC, toggleThuongVS } =
    payrollActions(ym, apply, load);
  // Ô TÊN → POPUP hồ sơ lương của thợ (ở NGAY trang này, khỏi rời bảng rồi phải
  // back + tải lại; vẫn mở được thành trang riêng bằng nút ↗ trong popup)
  const [sheetWid, setSheetWid] = useState<number | null>(null);
  const openWorker = (wid: number) => setSheetWid(wid);

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
                  {/* BHXH chỉ vào tổng quan khi tháng này CÓ trừ — xưởng chưa đóng thì
                      đừng chiếm 1 ô của thanh tóm tắt */}
                  {totals.thuong_cc + totals.thuong_vs ? (
                    <div class="pr-stat allowance"><span>Thưởng CC+VS</span>
                      <b>+{money(totals.thuong_cc + totals.thuong_vs)}</b></div>
                  ) : null}
                  {totals.bhxh ? <div class="pr-stat advance"><span>Trừ BHXH</span><b>−{money(totals.bhxh)}</b></div> : null}
                </div>
              </section>
            )}
            {view === "table" ? (
              <PayrollTable data={data} rows={rows} sort={sort} onSort={onSort} ym={ym}
                toggleType={toggleType} toggleWeekly={toggleWeekly} editMoc={editMoc}
                toggleThuongCC={toggleThuongCC} toggleThuongVS={toggleThuongVS}
                onCell={(wid, col) => setPop({ wid, col })} onName={openWorker} />
            ) : (
              <div class="pr-card-grid">
                {rows.map((r) => (
                  <PayrollCard key={r.worker_id} r={r} ym={ym}
                    toggleType={toggleType} toggleWeekly={toggleWeekly} editMoc={editMoc} editBhxh={editBhxh}
                    toggleThuongCC={toggleThuongCC} toggleThuongVS={toggleThuongVS}
                    openUng={openUng === r.worker_id} onToggleUng={() => toggleUng(r.worker_id)} advances={advs[r.worker_id]}
                    openPc={openPc === r.worker_id} onTogglePc={() => togglePc(r.worker_id)} allowances={allows[r.worker_id]}
                    apply={apply} setAdvs={setAdvs} setAllows={setAllows} />
                ))}
              </div>
            )}
          </>
        )}
      {sheetWid !== null && data && (() => {
        const r = data.workers.find((w) => w.worker_id === sheetWid);
        return r ? (
          <PayrollWorkerPopup ym={ym} r={r} onClose={() => setSheetWid(null)} apply={apply}
            toggleType={toggleType} toggleWeekly={toggleWeekly} editMoc={editMoc} editBhxh={editBhxh} />
        ) : null;
      })()}
      {pop && data && (() => {
        const r = data.workers.find((w) => w.worker_id === pop.wid);
        return r ? (
          <PayrollCellPopup ym={ym} r={r} col={pop.col}
            onClose={() => setPop(null)} onCol={(col) => setPop({ wid: pop.wid, col })}
            apply={apply} editMoc={editMoc} editBhxh={editBhxh} />
        ) : null;
      })()}
    </div>
  );
}

function PayrollTable({ data, rows, sort, onSort, ym, toggleType, toggleWeekly, editMoc,
  toggleThuongCC, toggleThuongVS, onCell, onName }: {
  data: PayrollMonth;
  rows: PayrollRow[];              // đã sắp theo cột đang chọn (cha lo)
  sort: Sort | null;
  onSort: (key: Sort["key"], num: boolean) => void;
  ym: string;                      // để chú thích nói rõ thưởng chỉ ăn tháng nào
  toggleType: (r: PayrollRow) => void; toggleWeekly: (r: PayrollRow) => void;
  editMoc: (r: PayrollRow) => void;
  toggleThuongCC: (r: PayrollRow) => void; toggleThuongVS: (r: PayrollRow) => void;
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
  // tên thợ dài cắt bằng ellipsis. Công (6,2) / Mốc (8,6) / Lương (8,8) rộng hơn phần
  // còn lại vì còn đeo dấu +TC (TG* gộp tăng ca vào công) / ↩ (mốc kế thừa) / ⁺ (lương
  // đã gộp phụ cấp phiếu) — đo bằng Playwright, hụt là chữ bị cắt ngay.
  // ⚠ CỘT THỢ HẸP LẠI TRÊN MOBILE (8em): cột này GHIM trái nên bề rộng của nó là phần
  // màn hình VĨNH VIỄN không dùng để xem số; 12em trên máy 360px nuốt gần nửa màn.
  // Ở mobile avatar cũng đã bị ẩn (media query 720px) nên 8em đủ chỗ cho tên + dòng
  // tiền bên dưới. Phải làm bằng JS: width nằm trong style inline của <col>, CSS
  // media query không đè được.
  const narrow = useNarrow();
  // ĐO LẠI 2026-08-04 bằng Playwright với nội dung DÀI NHẤT có thể của từng cột
  // (kể cả dòng TỔNG + các dấu ↩/⁺/số khoản) rồi + 0,35em đệm — tổng 106,7em ≈
  // 1366px, tức lọt màn 1440px không phải cuộn. Sửa số nào phải đo lại số đó.
  const COL_EM = [narrow ? 7 : 10.2, 4.9, 4.9, 8.3, 5.4, 3.3, 9.2, 8.2, 8.6, 7.2, 7.2, 9.3, 7.7, 7.5];
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
          {/* Tiêu đề BẤM ĐỂ SẮP XẾP: lần 1 sắp, lần 2 đảo chiều, lần 3 về mặc định.
              Nhãn/khoá cột lấy từ payrollSort.COLS — thứ tự phải khớp <td> ở thân. */}
          <thead>
            <tr>
              {COLS.map((c) => {
                const on = sort?.key === c.key;
                return (
                  <th key={c.key} class={c.key === "name" ? "pr-sticky pr-th-sort" : "pr-th-sort"}
                    role="button" tabIndex={0} aria-sort={on ? (sort!.dir === 1 ? "ascending" : "descending") : "none"}
                    title={`${c.title} — bấm để sắp xếp${on ? " (bấm nữa: đảo chiều / bỏ sắp)" : ""}`}
                    onClick={() => onSort(c.key, c.num)}
                    onKeyDown={(e: any) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSort(c.key, c.num); } }}>
                    {c.label}{on ? <span class="pr-sort-ar">{sort!.dir === 1 ? "▲" : "▼"}</span> : null}
                  </th>
                );
              })}
            </tr>
          </thead>
        </table>
      </div>
      <div class="pr-tbody-scroll" ref={bodyRef}
        onScroll={() => { if (headRef.current && bodyRef.current) headRef.current.scrollLeft = bodyRef.current.scrollLeft; }}>
        <table class="pr-table" style={tableStyle}>
          {cols}
          <tbody>
          {rows.map((r) => {
            const isTime = isTimeWage(r.wage_type);      // TG hoặc TG* → có mốc/ngày công
            const otCong = otInCong(r.wage_type);        // TG*: giờ TC đã gộp vào công
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
                  {/* Bỏ ảnh đại diện để nhường chỗ cho SỐ: dòng 2 = tổng nhận (chưa
                      trừ ứng), dòng 3 = TRUNG BÌNH 1 NGÀY CÔNG của tháng đó. */}
                  <span class="pr-worker">
                    <span class="pr-worker-main">
                      <span class="pr-worker-nm">{r.name}</span>
                      <span class="pr-worker-net"
                        title={`Tổng tiền nhận ${ymLabel(data.ym).toLowerCase()} = lương + phụ cấp + thưởng (chưa trừ ứng/BHXH)`}>
                        {money(tongNhan(r))}
                      </span>
                      <span class={r.cong > 0 ? "pr-worker-avg" : "pr-worker-avg is-zero"}
                        title={r.cong > 0
                          ? `Trung bình 1 ngày công = ${money(tongNhan(r))} ÷ ${congVN(r.cong)} công`
                          : "Tháng này chưa có ngày công nào nên chưa tính được trung bình"}>
                        {r.cong > 0 ? `${money(tongNhan(r) / r.cong)}/ngày` : "—/ngày"}
                      </span>
                    </span>
                  </span>
                </td>
                <td class="pr-td-mid">
                  <button class={isTime ? "chip pr-type time" : "chip pr-type"} onClick={() => toggleType(r)}
                    title={`Lương ${wageLabel(r.wage_type).toLowerCase()} — bấm đổi loại (SP → TG → TG*)`}>
                    {wageChip(r.wage_type)}
                  </button>
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
                {/* TG*: công ĐÃ gồm giờ tăng ca (dấu +TC), nên cột L.TC là "—" */}
                <td class={`pr-td-tap ${r.cong > 0 ? "pr-num" : "pr-num is-zero"}`} {...tap("cong")}
                  title={otCong ? "Ngày công (ĐÃ gộp giờ tăng ca — loại TG*) — bấm xem từng ngày"
                                : "Ngày công từ máy chấm — bấm xem từng ngày"}>
                  {r.cong > 0 ? congVN(r.cong) : "—"}
                  {otCong && r.ot_gio > 0 ? <sup title="đã gộp giờ tăng ca vào công"> +TC</sup> : null}
                </td>
                <td class={`pr-td-tap ${r.ot_gio > 0 ? "pr-num" : "pr-num is-zero"}`} {...tap("tc")}
                  title={otCong ? "Giờ tăng ca — loại TG* đã gộp số này vào ngày công, không trả riêng"
                                : "Số giờ tăng ca — bấm xem từng ngày"}>
                  {r.ot_gio > 0 ? congVN(r.ot_gio) : "—"}
                </td>
                {/* 2 NGUỒN LƯƠNG tách bạch — mỗi thợ chỉ ăn 1 trong 2, cột kia là "—".
                    Bấm mở popup diễn giải đúng cách tính của nguồn đó. */}
                <td class={`pr-td-tap ${r.luong_tg ? "pr-num" : "pr-num is-zero"}`} {...tap("luong_cong")}
                  title={!isTime ? `${r.name} ăn lương sản phẩm — không có lương theo công`
                    : otCong ? `Lương thời gian = mốc/26 × ${congVN(r.cong)} công (đã gồm ${congVN(r.ot_gio)}g tăng ca) — bấm xem cách tính`
                             : `Lương thời gian = lương ${congVN(r.cong)} công + lương tăng ca ×1,2 — bấm xem cách tính`}>
                  {isTime ? money(r.luong_tg) : "—"}
                </td>
                {/* Lương SP ĐÃ GỒM phụ cấp ghi trong phiếu SX (cột P.cấp là phụ cấp
                    THÁNG, khác hẳn) → nói trong tooltip + dấu ⁺ cho khỏi tưởng bỏ sót */}
                <td class={`pr-td-tap ${r.luong_sp ? "pr-num" : "pr-num is-zero"}`} {...tap("luong")}
                  title={!isTime
                    ? (r.pc_phieu ? `Lương sản phẩm — gồm ${money(r.pc_phieu)}đ phụ cấp ghi trong phiếu SX. Bấm xem cách tính`
                                  : "Lương sản phẩm tự tính từ báo cáo SX — bấm xem cách tính")
                    : `${r.name} ăn lương thời gian — không có lương sản phẩm`}>
                  {isTime ? "—" : <>{money(r.luong_sp)}{r.pc_phieu ? <sup title="đã gộp phụ cấp phiếu SX"> ⁺</sup> : null}</>}
                </td>
                <td class="pr-num pr-td-tap" title="Phụ cấp — bấm thêm/vô hiệu khoản" {...tap("pc")}>
                  <span class="pr-ung-btn">{money(r.phu_cap)}{r.pc_count ? <sup> {r.pc_count}</sup> : null}</span>
                </td>
                {/* 2 khoản THƯỞNG: bấm thẳng vào ô = BẬT/TẮT cho tháng đang xem
                    (không kế thừa sang tháng sau). Bật thì hiện số tiền, tắt hiện "—". */}
                <td class={`pr-num pr-td-tap ${r.cc_on ? "" : "is-zero"}`}
                  title={`Thưởng chuyên cần (cố định) — ${r.cc_on ? "ĐANG BẬT" : "đang tắt"}, bấm để ${r.cc_on ? "tắt" : "bật"} cho ${ymLabel(ym).toLowerCase()}`}>
                  <button class={r.cc_on ? "pr-bon on" : "pr-bon"} onClick={() => toggleThuongCC(r)}>
                    {r.cc_on ? money(r.thuong_cc) : "—"}
                  </button>
                </td>
                <td class={`pr-num pr-td-tap ${r.vs_on ? "" : "is-zero"}`}
                  title={`Thưởng vệ sinh = ${money(VS_MOI_NGAY)}đ × ${congVN(r.cong)} công — ${r.vs_on ? "ĐANG BẬT" : "đang tắt"}, bấm để ${r.vs_on ? "tắt" : "bật"} cho ${ymLabel(ym).toLowerCase()}`}>
                  <button class={r.vs_on ? "pr-bon on" : "pr-bon"} onClick={() => toggleThuongVS(r)}>
                    {r.vs_on ? money(r.thuong_vs) : "—"}
                  </button>
                </td>
                <td class="pr-num pr-td-tap" title="Ứng lương — bấm thêm/vô hiệu lần ứng" {...tap("ung")}>
                  <span class="pr-ung-btn">{money(r.ung)}{r.adv_count ? <sup> {r.adv_count}</sup> : null}</span>
                </td>
                {/* BHXH = số trừ hằng tháng, lưu theo TỪNG THÁNG + kế thừa như Mốc
                    (dấu ↩ = tháng này ăn theo mức đặt ở tháng trước). Bấm ô mở popup. */}
                <td class={`pr-td-tap ${r.bhxh ? "pr-num" : "pr-num is-zero"}`} {...tap("bhxh")}
                  title={`Trừ BHXH — ${r.bhxh_own ? "đặt riêng tháng này" : r.bhxh_ym ? `kế thừa mức đặt ở tháng ${r.bhxh_ym}` : "chưa đặt"}. Bấm để sửa`}>
                  <span class="pr-ung-btn">
                    {r.bhxh ? money(r.bhxh) : "đặt…"}
                    {r.bhxh && !r.bhxh_own ? <sup title="kế thừa từ tháng trước"> ↩</sup> : null}
                  </span>
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
                  <span class="pr-worker-net" title="Tổng tiền nhận cả xưởng (lương + phụ cấp + thưởng, chưa trừ ứng/BHXH)">
                    {money(t.luong + t.phu_cap + t.thuong + t.thuong_cc + t.thuong_vs)}
                  </span>
                  {(() => {
                    const c = data.workers.reduce((a, r) => a + (r.cong || 0), 0);
                    return <span class={c > 0 ? "pr-worker-avg" : "pr-worker-avg is-zero"}
                      title="Trung bình 1 ngày công của cả xưởng">
                      {c > 0 ? `${money((t.luong + t.phu_cap + t.thuong + t.thuong_cc + t.thuong_vs) / c)}/ngày` : "—/ngày"}
                    </span>;
                  })()}
                </span>
              </td><td></td><td></td><td></td>
              <td class="pr-num">{congVN(data.workers.reduce((a, r) => a + (r.cong || 0), 0))}</td>
              <td class="pr-num">{congVN(data.workers.reduce((a, r) => a + (r.ot_gio || 0), 0))}</td>
              <td class="pr-num">{money(data.workers.reduce((a, r) => a + (r.luong_tg || 0), 0))}</td>
              <td class="pr-num">{money(data.workers.reduce((a, r) => a + (r.luong_sp || 0), 0))}</td>
              <td class="pr-num">{money(t.phu_cap)}</td>
              <td class="pr-num">{money(t.thuong_cc)}</td>
              <td class="pr-num">{money(t.thuong_vs)}</td>
              <td class="pr-num">{money(t.ung)}</td>
              <td class="pr-num">{money(t.bhxh)}</td>
              <td class="pr-num pr-net-td">{money(t.thuc_lanh)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
