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
// CẢ view Bảng lẫn view Thẻ. 2 view tách ra file riêng vì trần 400 dòng:
// detail/PayrollTable.tsx (Bảng) + detail/PayrollCard.tsx (Thẻ).
// TÌM THỢ: ô tìm STICKY ngay dưới app-bar (không dấu, foldVN) — bảng dài mấy chục
// người, cuộn xuống giữa bảng vẫn gõ tìm được. Lọc áp cho CẢ 2 view; dòng TỔNG của
// bảng cộng theo số thợ ĐANG HIỆN (xem detail/PayrollTable.tsx).
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import {
  getMonthlyPayroll, isOffice, listPayrollAdvances, listPayrollAllowances,
  type PayrollMonth, type PayrollRow, type SalaryAdvance, type SalaryAllowance,
} from "../api";
import { moneyR as money, curYM, foldVN, shiftYM, ymLabel } from "../format";
import { PayrollCellPopup, type PayrollCol } from "../detail/PayrollCellPopup";
import { PayrollCard } from "../detail/PayrollCard";
import { PayrollTable } from "../detail/PayrollTable";
import { PayrollWorkerPopup } from "../detail/PayrollWorkerPopup";
import { payrollActions } from "../detail/payrollActions";
import { loadSort, nextSort, saveSort, sortRows, type Sort } from "../detail/payrollSort";
import { wageLabel } from "../detail/wageType";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { SearchBar } from "../ui/SearchBar";
import { Loading, EmptyState, ErrorState } from "../ui/states";

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
  // HÀNG VỪA THAO TÁC — giữ sáng cả sau khi đóng popup để khỏi lạc chỗ trong bảng dài
  const [activeWid, setActiveWid] = useState<number | null>(null);
  // Sắp xếp theo cột (null = thứ tự server). Nhớ trong localStorage; áp cả 2 view.
  const [sort, setSortState] = useState<Sort | null>(loadSort);
  const onSort = (key: any, num: boolean) => {
    const next = nextSort(sort, key, num);
    setSortState(next); saveSort(next);
  };
  // TÌM theo tên thợ, KHÔNG DẤU (gõ "phuong" ra "Phượng") — lọc trước rồi mới sắp
  const [q, setQ] = useState("");
  const rows = useMemo(() => {
    const all = data?.workers || [];
    const nq = foldVN(q.trim());
    return sortRows(nq ? all.filter((r) => foldVN(r.name).includes(nq)) : all, sort);
  }, [data, sort, q]);
  const filtering = !!q.trim();

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
  const openWorker = (wid: number) => { setActiveWid(wid); setSheetWid(wid); };

  const loadAdvances = async (wid: number) => {
    try { setAdvs((m) => ({ ...m, [wid]: [] })); const a = await listPayrollAdvances(ym, wid); setAdvs((m) => ({ ...m, [wid]: a })); } catch { /**/ }
  };
  const loadAllowances = async (wid: number) => {
    try { setAllows((m) => ({ ...m, [wid]: [] })); const a = await listPayrollAllowances(ym, wid); setAllows((m) => ({ ...m, [wid]: a })); } catch { /**/ }
  };
  const toggleUng = (wid: number) => { if (openUng === wid) { setOpenUng(null); return; } setOpenUng(wid); loadAdvances(wid); };
  const togglePc = (wid: number) => { if (openPc === wid) { setOpenPc(null); return; } setOpenPc(wid); loadAllowances(wid); };
  // Ô TÌM ghim dưới app-bar; thanh TIÊU ĐỀ BẢNG phải ghim ngay DƯỚI nó → đo chiều
  // cao thật của hàng tìm rồi đẩy vào biến CSS (--pr-search-h). Đo bằng JS vì chiều
  // cao đổi theo cỡ chữ/màn; hằng số cứng là lúc lệch lúc chồng lên nhau.
  const searchRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = searchRef.current;
    if (!el) return;
    const set = () => document.documentElement.style.setProperty("--pr-search-h", `${el.offsetHeight}px`);
    set();
    const ro = new ResizeObserver(set);
    ro.observe(el);
    return () => { ro.disconnect(); document.documentElement.style.removeProperty("--pr-search-h"); };
  }, []);

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

      {/* GHIM dưới app-bar: bảng dài mấy chục thợ, cuộn tới giữa vẫn tìm được ngay */}
      <div class="pr-searchrow" ref={searchRef}>
        <SearchBar value={q} onInput={setQ} placeholder="Tìm tên thợ…" />
        {filtering && data ? (
          <span class="pr-searchn">{rows.length}/{data.workers.length}</span>
        ) : null}
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
            {filtering && !rows.length ? (
              <EmptyState icon="🔍">Không có thợ nào tên khớp “{q.trim()}”.</EmptyState>
            ) : view === "table" ? (
              <PayrollTable data={data} rows={rows} sort={sort} onSort={onSort} ym={ym}
                toggleType={toggleType} toggleWeekly={toggleWeekly} editMoc={editMoc}
                toggleThuongCC={toggleThuongCC} toggleThuongVS={toggleThuongVS}
                onCell={(wid, col) => { setActiveWid(wid); setPop({ wid, col }); }} onName={openWorker}
                activeWid={activeWid} filtered={filtering} />
            ) : (
              <div class="pr-card-grid">
                {rows.map((r) => (
                  <PayrollCard key={r.worker_id} r={r} ym={ym} active={r.worker_id === activeWid}
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
