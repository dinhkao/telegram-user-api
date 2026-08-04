// POPUP Ô BẢNG LƯƠNG THÁNG — bấm 1 ô trong bảng (#/luong-thang) mở popup xem/thao
// tác đúng nội dung ô đó: Mốc = mốc lương THÁNG ĐANG XEM (lưu theo từng tháng,
// salary_store/moc.py) + khung TRAO ĐỔI gắn theo THỢ (scope worker_moc → dùng chung
// mọi tháng); Công/TC = chấm công từng ngày của thợ (luật quy công
// GIỐNG attendance_store/domain.work_stats); L.công/L.TC/Lương/Lãnh = diễn giải
// công thức; P.cấp/Ứng = panel thêm/vô hiệu khoản ngay tại chỗ (detail/EntryPanel);
// BHXH = số trừ hằng tháng của THÁNG ĐANG XEM (kế thừa theo tháng như mốc — 0 khác
// "bỏ đặt riêng", xem salary_store/bhxh.py).
// Data: getAttendanceSummary, payroll allowance/advance API. Cha (MonthlyPayroll)
// giữ state {wid, col} và truyền row TƯƠI mỗi lần data đổi.
import { useEffect, useState } from "preact/hooks";
import {
  addPayrollAdvance, addPayrollAllowance, getAttendanceSummary,
  listPayrollAdvances, listPayrollAllowances,
  setPayrollAdvanceNote, setPayrollAllowanceNote,
  voidPayrollAdvance, voidPayrollAllowance,
  type AttendanceDay, type PayrollMonth, type PayrollRow,
  type SalaryAdvance, type SalaryAllowance,
} from "../api";
import { Icon } from "../ui/Icon";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";
import { LoadingInline } from "../ui/states";
import { toast, promptDialog } from "../ui/feedback";

export type PayrollCol = "moc" | "cong" | "tc" | "luong_cong" | "luong_tc" | "luong"
  | "pc" | "ung" | "bhxh" | "net";

import { Comments } from "./Comments";
import { EntryPanel, PC_GOI_Y, UNG_GOI_Y } from "./EntryPanel";
import { isTimeWage, otInCong, wageLabel } from "./wageType";
import { moneyR as money, ymLabel } from "../format";
import { workStats } from "./attendanceStats";
const congVN = (n: number) => String(Math.round(n * 100) / 100).replace(".", ",");

const DOW = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
const dayVN = (ymd: string) => {
  const d = new Date(`${ymd}T00:00:00`);
  return `${DOW[d.getDay()]} ${Number(ymd.slice(8, 10))}/${Number(ymd.slice(5, 7))}`;
};

const TITLES: Record<PayrollCol, string> = {
  moc: "Mốc lương tháng", cong: "Ngày công", tc: "Giờ tăng ca",
  luong_cong: "Lương theo công", luong_tc: "Lương tăng ca", luong: "Lương",
  pc: "Phụ cấp", ung: "Ứng lương", bhxh: "Trừ BHXH", net: "Thực lãnh",
};

/** Số trừ BHXH này ở đâu ra — cùng cách nói với mocNguon (kế thừa theo tháng). */
export function bhxhNguon(r: PayrollRow, ym: string): string {
  if (r.bhxh_own) return `đặt riêng ${ymLabel(ym).toLowerCase()}`;
  if (r.bhxh_ym) return `theo mức đặt ở ${ymLabel(r.bhxh_ym).toLowerCase()}`;
  return "chưa đặt mức BHXH";
}

/** Mốc này ở đâu ra: đặt riêng tháng đang xem / kế thừa tháng nào / mốc hồ sơ thợ.
 *  Mốc lưu THEO TỪNG THÁNG (salary_store/moc.py) nên phải nói rõ, không thì người
 *  dùng tưởng sửa 1 lần là đổi hết mọi tháng như trước. */
export function mocNguon(r: PayrollRow, ym: string): string {
  if (!r.monthly_salary) return "chưa đặt mốc";
  if (r.moc_own) return `đặt riêng ${ymLabel(ym).toLowerCase()}`;
  if (r.moc_ym) return `theo mốc đặt ở ${ymLabel(r.moc_ym).toLowerCase()}`;
  return "mốc mặc định ở hồ sơ thợ";
}

export function PayrollCellPopup({ ym, r, col, onClose, onCol, apply, editMoc, editBhxh }: {
  ym: string; r: PayrollRow; col: PayrollCol;
  onClose: () => void; onCol: (c: PayrollCol) => void;
  apply: (d: PayrollMonth) => void;
  editMoc: (r: PayrollRow) => void;
  editBhxh: (r: PayrollRow) => void;
}) {
  usePopupBack(true, onClose);
  useScrollLock(true);
  const wid = r.worker_id;
  const isTime = isTimeWage(r.wage_type);
  const otCong = otInCong(r.wage_type);   // TG*: giờ TC gộp vào công, không trả riêng
  const dayRate = (r.monthly_salary || 0) / 26;

  // Chấm công tháng của thợ (cột Công/TC) — tải 1 lần khi cần
  const [att, setAtt] = useState<AttendanceDay[] | null>(null);
  useEffect(() => {
    if (col !== "cong" && col !== "tc") return;
    if (att) return;
    getAttendanceSummary(ym)
      .then((s) => setAtt(s.days.filter((d) => d.worker_id === wid)))
      .catch(() => setAtt([]));
  }, [col, ym, wid]);

  // Phụ cấp / ứng — panel thao tác tại chỗ
  const [allows, setAllows] = useState<SalaryAllowance[] | undefined>();
  const [advs, setAdvs] = useState<SalaryAdvance[] | undefined>();
  useEffect(() => {
    if (col === "pc") listPayrollAllowances(ym, wid).then(setAllows).catch(() => setAllows([]));
    if (col === "ung") listPayrollAdvances(ym, wid).then(setAdvs).catch(() => setAdvs([]));
  }, [col, ym, wid]);

  const voidReason = async (what: string) => {
    const reason = await promptDialog(`Lý do vô hiệu ${what}?`, { placeholder: "VD: ghi nhầm số tiền…", okLabel: "Vô hiệu" });
    if (reason === null) return null;
    if (!reason.trim()) { toast("Phải nhập lý do vô hiệu", "err"); return null; }
    return reason.trim();
  };
  const addAllow = async (a: number, note: string) => {
    try { apply(await addPayrollAllowance(ym, wid, a, note)); setAllows(await listPayrollAllowances(ym, wid)); }
    catch (e: any) { toast(e?.message || "Lỗi thêm phụ cấp", "err"); }
  };
  const voidAllow = async (id: number) => {
    const reason = await voidReason("khoản phụ cấp này");
    if (reason === null) return;
    try { apply(await voidPayrollAllowance(ym, id, reason)); setAllows(await listPayrollAllowances(ym, wid)); }
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
    try { apply(await setPayrollAllowanceNote(ym, id, next)); setAllows(await listPayrollAllowances(ym, wid)); toast("Đã lưu nội dung", "ok"); }
    catch (e: any) { toast(e?.message || "Lỗi lưu nội dung", "err"); }
  };
  const noteAdv = async (id: number, cur: string) => {
    const next = await askNote("Ghi chú lần ứng", cur);
    if (next === null) return;
    try { apply(await setPayrollAdvanceNote(ym, id, next)); setAdvs(await listPayrollAdvances(ym, wid)); toast("Đã lưu ghi chú", "ok"); }
    catch (e: any) { toast(e?.message || "Lỗi lưu ghi chú", "err"); }
  };
  const addAdv = async (a: number, note: string, date: string) => {
    try { apply(await addPayrollAdvance(ym, wid, a, date, note)); setAdvs(await listPayrollAdvances(ym, wid)); }
    catch (e: any) { toast(e?.message || "Lỗi thêm ứng", "err"); }
  };
  const voidAdv = async (id: number) => {
    const reason = await voidReason("lần ứng này");
    if (reason === null) return;
    try { apply(await voidPayrollAdvance(ym, id, reason)); setAdvs(await listPayrollAdvances(ym, wid)); }
    catch (e: any) { toast(e?.message || "Lỗi vô hiệu", "err"); }
  };

  // 1 dòng diễn giải: nhãn — giá trị; bấm được nếu có go (nhảy sang popup cột khác)
  const Row = ({ label, val, go, cls }: { label: any; val: any; go?: PayrollCol; cls?: string }) => (
    <button class={`pr-pop-row${go ? " tappable" : ""}${cls ? ` ${cls}` : ""}`} disabled={!go}
      onClick={go ? () => onCol(go) : undefined}>
      <span>{label}</span><b>{val}</b>
    </button>
  );

  const attList = (hl: "work" | "ot") => (
    att === null ? <p class="muted small"><LoadingInline label="Đang tải chấm công…" /></p>
    : !att.length ? <p class="muted small">Tháng này chưa có dữ liệu chấm công của {r.name}.</p>
    : (
      <div class="pr-pop-days">
        {att.map((d) => {
          const st = workStats(d.times || []);
          if (!st.work && !st.ot) return null;
          return (
            <div class="pr-pop-day" key={`${d.day}:${d.employee_code}`}>
              <span class="muted small">{dayVN(d.day)}{d.edited ? " ✏️" : ""}</span>
              <span class="pr-pop-times">{(d.times || []).join(" · ")}</span>
              {/* TG*: công của NGÀY cũng phải gộp giờ TC, không thì tổng ở trên (r.cong,
                  server đã gộp) không khớp tổng các dòng dưới */}
              <b class={hl === "work" ? "" : "muted"}>{congVN((st.work + (otCong ? st.ot : 0)) / 480)} công</b>
              <b class={hl === "ot" ? "t-warn" : "muted"}>
                {st.ot ? `${congVN(st.ot / 60)}g TC${otCong ? " → gộp" : ""}` : "—"}
              </b>
            </div>
          );
        })}
      </div>
    )
  );

  return (
    <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="modal-sheet pr-pop-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head"><Icon name="wallet" size={18} /> {r.name} — {TITLES[col]}</div>

        {col === "moc" && (
          isTime ? (
            <>
              <Row label={`Mốc lương ${ymLabel(ym).toLowerCase()}`}
                val={<button class="pr-ung-btn" onClick={() => editMoc(r)}>{r.monthly_salary ? `${money(r.monthly_salary)}đ` : "đặt…"}</button>}
                cls="hl" />
              <p class="muted small">{mocNguon(r, ym)} — mốc lưu theo TỪNG THÁNG: sửa ở đây áp dụng
                từ {ymLabel(ym).toLowerCase()} trở đi, các tháng trước giữ nguyên số cũ.</p>
              <Row label="Lương 1 công (mốc ÷ 26)" val={`${money((r.monthly_salary || 0) / 26)}đ`} />
              <Row label="Lương theo công tháng này" val={`${money(r.luong_cong)}đ`} go="luong_cong" />
              <button class="btn block" onClick={() => editMoc(r)}>
                ✏️ {r.monthly_salary ? `Sửa mốc ${ymLabel(ym).toLowerCase()}` : `Đặt mốc ${ymLabel(ym).toLowerCase()}`}
              </button>
              {/* Trao đổi gắn theo THỢ (scope worker_moc/worker_id) → hiện GIỐNG NHAU ở
                  mọi tháng. Không cho ghim lên bảng tin: đây là chuyện tiền lương. */}
              <Comments base={`/api/media/worker_moc/${wid}`} allowPin={false} />
              <p class="muted small">Trao đổi về mốc lương của {r.name} — dùng chung cho mọi tháng.</p>
            </>
          ) : (
            <p class="muted small">{r.name} hưởng lương SẢN PHẨM — không có mốc lương tháng.
              Đổi sang lương thời gian ở ô "Loại" nếu cần.</p>
          )
        )}

        {(col === "cong" || col === "tc") && (
          <>
            <div class="pr-pop-sum">
              <Row label={otCong ? "Tổng công (ngày đủ 2 ca = 1, ĐÃ gộp tăng ca)" : "Tổng công (ngày đủ 2 ca = 1)"}
                val={congVN(r.cong)} cls={col === "cong" ? "hl" : ""} />
              <Row label="Tổng tăng ca" val={`${congVN(r.ot_gio)} giờ`} cls={col === "tc" ? "hl" : ""} />
            </div>
            {otCong ? <p class="muted small">Loại <b>TG*</b>: giờ tăng ca gộp thẳng vào ngày công
              (1 công = 8 giờ) và trả theo đơn giá công — KHÔNG có tiền tăng ca ×1,2 riêng.</p> : null}
            {attList(col === "cong" ? "work" : "ot")}
            <a class="btn block" href={`#/cham-cong/${wid}?ym=${encodeURIComponent(ym)}`}>
              🕐 Chấm công tháng của {r.name} (xem/sửa giờ)
            </a>
          </>
        )}

        {col === "luong_cong" && (
          <>
            {isTime ? (
              <>
                <Row label={`Mốc lương ${ymLabel(ym).toLowerCase()} (${mocNguon(r, ym)})`}
                  val={r.monthly_salary ? `${money(r.monthly_salary)}đ` : "đặt…"} go="moc" />
                <Row label="Lương 1 công (mốc ÷ 26)" val={`${money(dayRate)}đ`} />
                <Row label={otCong ? `Ngày công (đã gộp ${congVN(r.ot_gio)}g tăng ca)` : "Ngày công"}
                  val={congVN(r.cong)} go="cong" />
                <Row label={<b>Lương công = {money(dayRate)} × {congVN(r.cong)}</b>} val={`${money(r.luong_cong)}đ`} cls="hl" />
                {otCong ? <p class="muted small">TG*: đây là TOÀN BỘ lương thời gian của tháng —
                  giờ tăng ca đã nằm trong số công, không cộng thêm lương tăng ca.</p> : null}
              </>
            ) : <p class="muted small">{r.name} hưởng lương SẢN PHẨM — không tính lương theo công.</p>}
          </>
        )}

        {col === "luong_tc" && (
          <>
            {otCong ? (
              <>
                <Row label="Giờ tăng ca" val={`${congVN(r.ot_gio)} giờ`} go="tc" />
                <Row label={<b>Lương tăng ca riêng</b>} val="không có" />
                <p class="muted small">{r.name} hưởng lương <b>TG*</b>: giờ tăng ca đã GỘP vào ngày
                  công ({congVN(r.cong)} công) và trả theo đơn giá công, nên không tính tiền tăng ca
                  ×1,2 riêng. Xem ở "Lương theo công".</p>
                <Row label="Lương theo công (đã bao gồm tăng ca)" val={`${money(r.luong_cong)}đ`} go="luong_cong" />
              </>
            ) : isTime ? (
              <>
                <Row label="Giờ tăng ca" val={`${congVN(r.ot_gio)} giờ`} go="tc" />
                <Row label="Đơn giá giờ TC (mốc ÷ 26 ÷ 8 × 1,2)" val={`${money(dayRate / 8 * 1.2)}đ/giờ`} />
                <Row label={<b>Lương tăng ca</b>} val={`${money(r.luong_tc)}đ`} cls="hl" />
              </>
            ) : <p class="muted small">{r.name} hưởng lương SẢN PHẨM — không tính lương tăng ca theo giờ.</p>}
          </>
        )}

        {col === "luong" && (
          isTime ? (
            <>
              <Row label={otCong ? `Lương theo công (${congVN(r.cong)} công, đã gộp ${congVN(r.ot_gio)}g TC)`
                                 : "Lương theo công"}
                val={`${money(r.luong_cong)}đ`} go="luong_cong" />
              {otCong
                ? <Row label="Lương tăng ca riêng (TG* không có)" val="—" go="luong_tc" />
                : <Row label="Lương tăng ca (×1,2)" val={`${money(r.luong_tc)}đ`} go="luong_tc" />}
              <Row label={<b>Lương {wageLabel(r.wage_type).toLowerCase()}</b>} val={`${money(r.luong)}đ`} cls="hl" />
            </>
          ) : (
            <>
              {/* Lương SP = tiền cây + PHỤ CẤP GHI TRONG PHIẾU SX. Phụ cấp phiếu đã nằm
                  trong con số Lương (cột P.cấp của bảng là phụ cấp THÁNG, khác hẳn) →
                  tách 2 dòng cho khỏi tưởng bảng lương bỏ sót phụ cấp phiếu. */}
              <Row label="Tiền sản phẩm (cây × đơn giá phiếu)" val={`${money(r.luong - (r.pc_phieu || 0))}đ`} />
              <Row label="Phụ cấp ghi trong phiếu SX" val={`+${money(r.pc_phieu || 0)}đ`} />
              <Row label="Lương sản phẩm (tự tính từ báo cáo SX)" val={`${money(r.luong)}đ`} cls="hl" />
              <p class="muted small">= tổng cây × đơn giá chốt theo từng phiếu SX trong tháng
                {r.pc_phieu ? <> + phụ cấp phiếu ({money(r.pc_phieu)}đ — đã gộp sẵn ở đây,
                  KHÁC cột P.cấp = phụ cấp tháng)</> : <> (tháng này không có phụ cấp phiếu)</>}.</p>
              <a class="btn block" href={`#/sx-tho/${encodeURIComponent(r.name)}`}>🏭 Chi tiết sản xuất của thợ</a>
              <a class="btn block" href="#/bao-cao">📄 Phiếu báo cáo SX</a>
            </>
          )
        )}

        {col === "bhxh" && (
          <>
            <Row label={`Trừ BHXH ${ymLabel(ym).toLowerCase()}`}
              val={<button class="pr-ung-btn" onClick={() => editBhxh(r)}>{r.bhxh ? `${money(r.bhxh)}đ` : "đặt…"}</button>}
              cls="hl" />
            <p class="muted small">{bhxhNguon(r, ym)} — mức BHXH lưu theo TỪNG THÁNG: sửa ở đây áp
              dụng từ {ymLabel(ym).toLowerCase()} trở đi, các tháng trước giữ nguyên số cũ.
              Gõ <b>0</b> = từ tháng này thôi trừ; để trống = bỏ mức riêng, kế thừa lại số trước đó.</p>
            <Row label="Tổng nhận trước khi trừ (lương + phụ cấp)" val={`${money(r.luong + r.phu_cap + r.thuong)}đ`} />
            <Row label="Đã ứng" val={`−${money(r.ung)}đ`} go="ung" />
            <Row label={<b>Thực lãnh sau khi trừ BHXH</b>} val={`${money(r.thuc_lanh)}đ`} go="net" />
            <button class="btn block" onClick={() => editBhxh(r)}>
              ✏️ {r.bhxh ? `Sửa mức BHXH ${ymLabel(ym).toLowerCase()}` : `Đặt mức BHXH ${ymLabel(ym).toLowerCase()}`}
            </button>
          </>
        )}

        {col === "pc" && (
          <>
            <EntryPanel entries={allows} addPlaceholder="Số tiền phụ cấp"
              submitLabel="Thêm phụ cấp" noteLabel="Nội dung phụ cấp"
              notePlaceholder="VD: ăn trưa, xăng xe…" noteSuggestions={PC_GOI_Y}
              onAdd={(a, note) => addAllow(a, note)} onDel={voidAllow} onNote={noteAllow} />
            <a class="btn block" href={`#/nhap-phu-cap?ym=${encodeURIComponent(ym)}&worker_id=${wid}`}>📋 Trang nhập phụ cấp</a>
          </>
        )}

        {col === "ung" && (
          <>
            <EntryPanel entries={advs} showDate addPlaceholder="Số tiền ứng"
              submitLabel="Ghi ứng" notePlaceholder="VD: ứng mua xe…" noteSuggestions={UNG_GOI_Y}
              onAdd={(a, note, date) => addAdv(a, note, date)} onDel={voidAdv} onNote={noteAdv}
              extra={r.weekly && r.ung_weekly > 0 ? (
                <div class="pr-adv-row pr-adv-weekly">
                  <span class="muted small">Lương tuần</span><b>{money(r.ung_weekly)}</b>
                  <span class="muted small pr-adv-note">tự động = lương SP</span>
                </div>
              ) : null} />
            <a class="btn block" href={`#/nhap-ung?ym=${encodeURIComponent(ym)}&worker_id=${wid}`}>📋 Trang nhập ứng</a>
          </>
        )}

        {col === "net" && (
          <>
            <Row label="Lương" val={`${money(r.luong)}đ`} go="luong" />
            <Row label={`Phụ cấp${r.pc_count ? ` (${r.pc_count} khoản)` : ""}`} val={`+${money(r.phu_cap)}đ`} go="pc" />
            {/* 2 khoản thưởng bật/tắt — chỉ hiện dòng khi ĐANG BẬT, khỏi rối */}
            {r.cc_on ? <Row label="Thưởng chuyên cần" val={`+${money(r.thuong_cc)}đ`} /> : null}
            {r.vs_on ? <Row label={`Thưởng vệ sinh (${congVN(r.cong)} công)`} val={`+${money(r.thuong_vs)}đ`} /> : null}
            {r.thuong ? <Row label="Thưởng (tháng cũ)" val={`+${money(r.thuong)}đ`} /> : null}
            <Row label={`Đã ứng${r.adv_count ? ` (${r.adv_count} lần)` : ""}`} val={`−${money(r.ung)}đ`} go="ung" />
            <Row label={`Trừ BHXH${r.bhxh ? ` (${bhxhNguon(r, ym)})` : ""}`} val={`−${money(r.bhxh)}đ`} go="bhxh" />
            <Row label={<b>Thực lãnh</b>} val={`${money(r.thuc_lanh)}đ`} cls={r.thuc_lanh < 0 ? "hl t-danger" : "hl"} />
          </>
        )}

        <button class="btn sh-cancel" onClick={onClose}>Đóng</button>
      </div>
    </div>
  );
}
