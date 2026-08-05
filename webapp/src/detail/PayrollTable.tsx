// VIEW BẢNG của bảng lương tháng (#/luong-thang) — tách khỏi pages/MonthlyPayroll.tsx
// vì trần 400 dòng/file (view Thẻ đã tách trước ở detail/PayrollCard.tsx).
// Nhận `rows` ĐÃ lọc + ĐÃ sắp từ trang cha; MỌI ô số bấm được → popup đúng cột
// (detail/PayrollCellPopup), ô TÊN → popup hồ sơ lương thợ.
// ⚠ Dòng TỔNG (tfoot) cộng theo `rows` ĐANG HIỆN chứ không lấy data.totals — đang
// tìm 3 thợ mà chân bảng cộng cả xưởng thì đọc sai ngay. Không lọc thì 2 số trùng
// khít vì server cũng cộng dồn số ĐÃ làm tròn của từng dòng (salary_store/store.py).
import { useEffect, useRef, useState } from "preact/hooks";
import { type PayrollMonth, type PayrollRow } from "../api";
import { moneyR as money, ymLabel } from "../format";
import { type PayrollCol } from "./PayrollCellPopup";
import { COLS, type Sort } from "./payrollSort";
import { isTimeWage, otInCong, wageChip, wageLabel } from "./wageType";

const congVN = (n: number) => String(Math.round(n * 100) / 100).replace(".", ",");
// Gương của salary_store/bonus.THUONG_VE_SINH_MOI_NGAY — CHỈ dùng cho chú thích
// ("12.000đ × N công"); số tiền thật luôn do server tính, client không tự cộng.
const VS_MOI_NGAY = 12000;
/** TỔNG TIỀN NHẬN của 1 thợ trong tháng (CHƯA trừ ứng/BHXH) — phải gồm CẢ 2 khoản
 *  thưởng chuyên cần/vệ sinh, không thì bật/tắt thưởng mà số xanh dưới tên đứng im. */
const tongNhan = (r: PayrollRow) =>
  r.luong + r.phu_cap + r.thuong + r.thuong_cc + r.thuong_vs + r.cho_hang;
const sum = (rows: PayrollRow[], f: (r: PayrollRow) => number) => rows.reduce((a, r) => a + (f(r) || 0), 0);
/** TỔNG cột LÃNH = tiền THỰC SỰ phải chi → CHỈ cộng thợ dương (Duy chốt 2026-08-05).
 *  Thợ âm (ứng/BHXH vượt lương) tháng này nhận 0 và nợ lại, không làm giảm tiền phải
 *  trả cho người khác. Luật này PHẢI khớp server (salary_store/store.compute_month_payroll)
 *  — lệch 1 bên là chân bảng khác thanh tóm tắt. */
const sumLanh = (rows: PayrollRow[]) => rows.reduce((a, r) => a + Math.max(0, r.thuc_lanh || 0), 0);
const sumAm = (rows: PayrollRow[]) => rows.reduce((a, r) => a + Math.max(0, -(r.thuc_lanh || 0)), 0);

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

export function PayrollTable({ data, rows, sort, onSort, ym, toggleType, toggleWeekly, editMoc,
  toggleThuongCC, toggleThuongVS, editChoHang, onCell, onName, activeWid, filtered }: {
  data: PayrollMonth;
  rows: PayrollRow[];              // đã lọc + sắp theo cột đang chọn (cha lo)
  sort: Sort | null;
  onSort: (key: Sort["key"], num: boolean) => void;
  ym: string;                      // để chú thích nói rõ thưởng chỉ ăn tháng nào
  toggleType: (r: PayrollRow) => void; toggleWeekly: (r: PayrollRow) => void;
  editMoc: (r: PayrollRow) => void;
  toggleThuongCC: (r: PayrollRow) => void; toggleThuongVS: (r: PayrollRow) => void;
  editChoHang: (r: PayrollRow) => void;   // ô Chờ hàng: bấm là gõ số tiền
  onCell: (wid: number, col: PayrollCol) => void;
  onName: (wid: number) => void;   // ô TÊN → popup lương của thợ
  activeWid: number | null;        // hàng vừa thao tác → tô sáng
  filtered: boolean;               // đang lọc bằng ô tìm → chân bảng nói rõ "n/N thợ"
}) {
  // SỐ ĐẦY ĐỦ (không rút gọn) → bảng RỘNG hơn màn: thân cuộn NGANG, cột Thợ ghim
  // trái; header tách thanh sticky top (dưới app-bar + ô tìm) + scrollLeft đồng bộ
  // từ thân — cùng kỹ thuật lưới chấm công.
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
  // (cột "Chờ hàng" thêm 2026-08-05 — 8em: nhãn 8 ký tự + số tới 7 chữ số)
  const COL_EM = [narrow ? 7 : 10.2, 4.9, 4.9, 8.3, 5.4, 3.3, 9.2, 8.2, 8.6, 7.2, 7.2, 8, 9.3, 7.7, 7.5];
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
  const congAll = sum(rows, (r) => r.cong);
  const amAll = sumAm(rows);                       // tổng phần ÂM (thợ nợ lại)
  const amCount = rows.filter((r) => r.thuc_lanh < 0).length;
  const nhanAll = sum(rows, tongNhan);
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
              <tr key={r.worker_id} class={r.worker_id === activeWid ? "is-active" : ""}>
                <td class="pr-sticky pr-td-name pr-td-tap" role="button" tabIndex={0}
                  title="Mở trang lương tháng của thợ"
                  onClick={() => onName(r.worker_id)}
                  onKeyDown={(e: any) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onName(r.worker_id); } }}>
                  {/* Dưới tên = TỔNG TIỀN NHẬN ĐƯỢC của tháng (lương + phụ cấp + thưởng),
                      CHƯA trừ ứng — cố ý KHÁC cột Lãnh (thực lãnh = đã trừ ứng). Cột Thợ
                      ghim trái nên thấy ngay số này khỏi phải cuộn ngang.
                      Bỏ ảnh đại diện để nhường chỗ cho SỐ: dòng 2 = tổng nhận (chưa
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
                    onClick={() => toggleWeekly(r)} style="cursor:pointer" title="Nhận lương tuần (áp cho cả lương SP lẫn lương thời gian) — bật thì lương tháng coi như đã trả, trừ hết vào ứng"><span class="tgl-knob" /></span>
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
                  title={r.cong_manual
                    ? `Ngày công GÕ TAY (máy chấm quy ra ${congVN(r.cong_auto ?? r.cong)}) — bấm để sửa`
                    : otCong ? "Ngày công (ĐÃ gộp giờ tăng ca — loại TG*) — bấm xem/nhập tay"
                             : "Ngày công từ máy chấm — bấm xem từng ngày / nhập tay"}>
                  {r.cong > 0 ? congVN(r.cong) : "—"}
                  {otCong && r.ot_gio > 0 ? <sup title="đã gộp giờ tăng ca vào công"> +TC</sup> : null}
                  {r.cong_manual ? <sup title={`gõ tay — máy chấm quy ra ${congVN(r.cong_auto ?? r.cong)}`}> ✎</sup> : null}
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
                  {isTime ? "—" : <>{money(r.luong_sp)}{r.pc_phieu ? <sup title="đã gộp phụ cấp phiếu SX"> ⁺</sup> : null}
                    {r.tru_an ? <sup class="t-danger" title={`đã trừ ẩn ${money(r.tru_an)}đ (phiếu in của thợ không hiện)`}> ▾</sup> : null}</>}
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
                {/* LƯƠNG CHỜ HÀNG: bấm ô là gõ thẳng số tiền (1 số/tháng nên không
                    cần panel nhiều khoản như phụ cấp). Chỉ ăn tháng đang xem. */}
                <td class={`pr-num pr-td-tap ${r.cho_hang ? "" : "is-zero"}`}
                  title={`Lương chờ hàng ${ymLabel(ym).toLowerCase()} — bấm để nhập số tiền`}>
                  <button class="pr-bon" onClick={() => editChoHang(r)}>
                    {r.cho_hang ? money(r.cho_hang) : "—"}
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
                  <span class="pr-worker-nm">
                    Tổng{filtered ? <small class="pr-foot-n"> {rows.length}/{data.workers.length}</small> : null}
                  </span>
                  <span class="pr-worker-net" title="Tổng tiền nhận của các thợ ĐANG HIỆN (lương + phụ cấp + thưởng, chưa trừ ứng/BHXH)">
                    {money(nhanAll)}
                  </span>
                  <span class={congAll > 0 ? "pr-worker-avg" : "pr-worker-avg is-zero"}
                    title="Trung bình 1 ngày công của các thợ đang hiện">
                    {congAll > 0 ? `${money(nhanAll / congAll)}/ngày` : "—/ngày"}
                  </span>
                </span>
              </td><td></td><td></td><td></td>
              <td class="pr-num">{congVN(congAll)}</td>
              <td class="pr-num">{congVN(sum(rows, (r) => r.ot_gio))}</td>
              <td class="pr-num">{money(sum(rows, (r) => r.luong_tg))}</td>
              <td class="pr-num">{money(sum(rows, (r) => r.luong_sp))}</td>
              <td class="pr-num">{money(sum(rows, (r) => r.phu_cap))}</td>
              <td class="pr-num">{money(sum(rows, (r) => r.thuong_cc))}</td>
              <td class="pr-num">{money(sum(rows, (r) => r.thuong_vs))}</td>
              <td class="pr-num">{money(sum(rows, (r) => r.cho_hang))}</td>
              <td class="pr-num">{money(sum(rows, (r) => r.ung))}</td>
              <td class="pr-num">{money(sum(rows, (r) => r.bhxh))}</td>
              <td class="pr-num pr-net-td" title={amAll
                ? `Chỉ cộng thợ dương. ${amCount} thợ đang âm ${money(amAll)}đ (ứng/BHXH vượt lương) — tháng này nhận 0 và nợ lại.`
                : "Tổng tiền thực phải chi tháng này"}>
                {money(sumLanh(rows))}
                {amAll ? <sup class="t-danger" title={`${amCount} thợ đang âm ${money(amAll)}đ — không trừ vào tổng`}> *</sup> : null}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
