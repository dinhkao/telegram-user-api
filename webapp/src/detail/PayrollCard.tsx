// THẺ 1 THỢ ở bảng lương tháng (#/luong-thang, view "Thẻ") — cùng dữ liệu với view
// Bảng nhưng dạng thẻ cho điện thoại: thực lãnh + lương/phụ cấp/ứng + mốc lương (thợ
// lương thời gian) + 2 khối gập chi tiết PHỤ CẤP và ỨNG (EntryPanel dùng chung với
// popup ô bảng — xem luật ĐỒNG BỘ 2 CHỖ trong PayrollCellPopup).
// Tách khỏi pages/MonthlyPayroll.tsx (file đó chạm trần 400 dòng khi thêm sắp xếp).
import {
  addPayrollAdvance, addPayrollAllowance, listPayrollAdvances, listPayrollAllowances,
  setPayrollAdvanceNote, setPayrollAllowanceNote, setPayrollAllowancePrintNote, voidPayrollAdvance, voidPayrollAllowance,
  type PayrollMonth, type PayrollRow, type SalaryAdvance, type SalaryAllowance,
} from "../api";
import { moneyR as money } from "../format";
import { EntryPanel, PC_GOI_Y, UNG_GOI_Y } from "./EntryPanel";
import { PrevAllowances, allowCalcOf, copyAmount } from "./PrevAllowances";
import { pctBaseOf } from "./PayrollCellPopup";
import { isTimeWage, otInCong, wageLabel } from "./wageType";
import { toast, promptDialog } from "../ui/feedback";

const initials = (name: string) => name.trim().split(/\s+/).slice(-2).map((part) => part[0] || "").join("").toUpperCase();

export function PayrollCard({ r, ym, active, toggleType, toggleWeekly, editMoc, editBhxh,
  toggleThuongCC, toggleThuongVS, editChoHang,
  openUng, onToggleUng, advances, openPc, onTogglePc, allowances, apply, setAdvs, setAllows }: {
  r: PayrollRow; ym: string; active?: boolean;
  toggleType: (r: PayrollRow) => void; toggleWeekly: (r: PayrollRow) => void;
  editMoc: (r: PayrollRow) => void; editBhxh: (r: PayrollRow) => void;
  toggleThuongCC: (r: PayrollRow) => void; toggleThuongVS: (r: PayrollRow) => void;
  editChoHang: (r: PayrollRow) => void;
  openUng: boolean; onToggleUng: () => void; advances?: SalaryAdvance[];
  openPc: boolean; onTogglePc: () => void; allowances?: SalaryAllowance[];
  apply: (d: PayrollMonth) => void;
  setAdvs: (f: (m: Record<number, SalaryAdvance[]>) => Record<number, SalaryAdvance[]>) => void;
  setAllows: (f: (m: Record<number, SalaryAllowance[]>) => Record<number, SalaryAllowance[]>) => void;
}) {
  const isTime = isTimeWage(r.wage_type);
  const otCong = otInCong(r.wage_type);     // TG*: giờ TC gộp vào công, không trả riêng
  const wid = r.worker_id;

  const addAllow = async (a: number, note: string, calc?: { kind: "pct" | "day"; value: number } | null,
                         printNote?: string) => {
    // PHẢI toast: thêm xong mà im lặng thì người dùng tưởng bấm hụt, bấm lại → ghi 2 lần
    try { apply(await addPayrollAllowance(ym, wid, a, note, calc, printNote)); const l = await listPayrollAllowances(ym, wid); setAllows((m) => ({ ...m, [wid]: l }));
      toast(`Đã ghi phụ cấp ${money(a)}đ cho ${r.name}`, "ok"); }
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
  // 🖨 chữ IN TRÊN PHIẾU của khoản (rỗng = phiếu in nội dung khoản như cũ)
  const printAllow = async (id: number, cur: string) => {
    const next = await promptDialog(
      "Chữ in trên phiếu lương cho khoản này\nĐể trống = in theo nội dung khoản.",
      { initial: cur, placeholder: "VD: Phụ cấp tháng 7", okLabel: "Lưu" });
    if (next === null || next.trim() === cur) return;
    try { apply(await setPayrollAllowancePrintNote(ym, id, next.trim())); const l = await listPayrollAllowances(ym, wid); setAllows((m) => ({ ...m, [wid]: l }));
      toast("Đã lưu chữ in trên phiếu", "ok"); }
    catch (e: any) { toast(e?.message || "Lỗi lưu chữ in", "err"); }
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
    try { apply(await addPayrollAdvance(ym, wid, a, date, note)); const l = await listPayrollAdvances(ym, wid); setAdvs((m) => ({ ...m, [wid]: l }));
      toast(`Đã ghi ứng ${money(a)}đ cho ${r.name}`, "ok"); }
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
    <section class={active ? "card pr-card is-active" : "card pr-card"}>
      <div class="pr-top">
        <div class="pr-person">
          <span class="pr-avatar large">{initials(r.name)}</span>
          <div>
            <a class="pr-name-link" href={`#/luong-thang/${wid}?ym=${encodeURIComponent(ym)}`}>{r.name}</a>
            <span class="pr-person-sub">Lương {wageLabel(r.wage_type).toLowerCase()}</span>
          </div>
        </div>
        <div class="pr-card-net"><span>Thực lãnh</span><b class={r.thuc_lanh < 0 ? "t-danger" : ""}>{money(r.thuc_lanh)}</b></div>
      </div>

      <div class="pr-card-metrics">
        <div class="pr-card-metric"><span>Lương</span><b>{money(r.luong)}</b></div>
        <div class="pr-card-metric"><span>Phụ cấp</span><a href={`#/nhap-phu-cap?ym=${encodeURIComponent(ym)}&worker_id=${wid}`}>{money(r.phu_cap)}</a></div>
        <div class="pr-card-metric advance"><span>Đã ứng</span><a href={`#/nhap-ung?ym=${encodeURIComponent(ym)}&worker_id=${wid}`}>{money(r.ung)}</a></div>
        {/* 2 khoản THƯỞNG: bấm là bật/tắt cho THÁNG ĐANG XEM (không kế thừa) */}
        <div class="pr-card-metric"><span>Ch.cần</span>
          <button class={r.cc_on ? "pr-bon on" : "pr-bon"} onClick={() => toggleThuongCC(r)}
            title={`Thưởng chuyên cần — bấm để ${r.cc_on ? "tắt" : "bật"} cho tháng này`}>
            {r.cc_on ? money(r.thuong_cc) : "— bật"}
          </button>
        </div>
        <div class="pr-card-metric"><span>Vệ sinh</span>
          <button class={r.vs_on ? "pr-bon on" : "pr-bon"} onClick={() => toggleThuongVS(r)}
            title={`Thưởng vệ sinh = 12.000đ × ${r.cong} công — bấm để ${r.vs_on ? "tắt" : "bật"} cho tháng này`}>
            {r.vs_on ? money(r.thuong_vs) : "— bật"}
          </button>
        </div>
        {/* LƯƠNG CHỜ HÀNG: bấm là gõ số tiền cho THÁNG ĐANG XEM (không kế thừa) */}
        <div class="pr-card-metric"><span>Chờ hàng</span>
          <button class="pr-bon" onClick={() => editChoHang(r)}
            title="Lương chờ hàng — bấm để nhập số tiền cho tháng này">
            {r.cho_hang ? money(r.cho_hang) : "— nhập"}
          </button>
        </div>
        {/* BHXH: luôn hiện (kể cả chưa đặt) để bấm đặt được ngay — giống cột BHXH
            của view Bảng; dấu ↩ = tháng này kế thừa mức đặt ở tháng trước. */}
        <div class="pr-card-metric advance"><span>Trừ BHXH</span>
          <button class="pr-ung-btn" onClick={() => editBhxh(r)}
            title={r.bhxh_own ? "Đặt riêng tháng này — bấm để sửa"
              : r.bhxh_ym ? `Kế thừa mức đặt ở tháng ${r.bhxh_ym} — bấm để sửa`
              : "Chưa đặt mức BHXH — bấm để đặt"}>
            {r.bhxh ? `${money(r.bhxh)}${r.bhxh_own ? "" : " ↩"}` : "đặt…"}
          </button>
        </div>
      </div>

      {isTime && (
        <div class="pr-moc-row">
          <button class="pr-ung-btn" onClick={() => editMoc(r)}
            title={`Mốc của tháng đang xem — ${r.moc_own ? "đặt riêng tháng này" : r.moc_ym ? `kế thừa mốc đặt ở tháng ${r.moc_ym}` : "mốc hồ sơ thợ"}. Bấm để sửa`}>
            Mốc {r.monthly_salary ? money(r.monthly_salary) : "chưa đặt — bấm sửa"}
            {r.monthly_salary && !r.moc_own ? " ↩" : ""}
          </button>
          <span class="muted small">
            {otCong
              ? <>{r.cong} công (đã gộp {r.ot_gio}g tăng ca) = {money(r.luong_cong)}đ · không trả TC riêng</>
              : <>{r.cong} công = {money(r.luong_cong)}đ · TC {r.ot_gio}g = {money(r.luong_tc)}đ (×1,2)</>}
            {" "}<a href={`#/cham-cong/${wid}?ym=${encodeURIComponent(ym)}`}>→ chấm công</a>
          </span>
        </div>
      )}
      <div class="pr-card-tools">
        <button class={isTime ? "chip pr-type time" : "chip pr-type"} onClick={() => toggleType(r)}
          title="Bấm để đổi loại lương (SP → TG → TG*)">{wageLabel(r.wage_type)}</button>
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
        submitLabel="Thêm phụ cấp" noteLabel="Nội dung phụ cấp"
        notePlaceholder="VD: ăn trưa, xăng xe…" noteSuggestions={PC_GOI_Y} pctBase={pctBaseOf(r)} dayBase={{ days: r.cong || 0 }}
        onAdd={(a, note, _d, calc, pn) => addAllow(a, note, calc, pn)} onDel={voidAllow}
        onNote={noteAllow} onPrintNote={printAllow}
        prev={<PrevAllowances ym={ym} wid={wid}
          onCopy={(e) => addAllow(copyAmount(e, pctBaseOf(r).value, r.cong || 0),
            e.note, allowCalcOf(e), e.print_note)} />} />}
      <div class="pr-adv-toggle">
        <span>Chi tiết ứng lương {r.adv_count ? <span class="muted small">· {r.adv_count} lần nhập tay</span> : null}</span>
        <button class="pr-toggle-btn" onClick={onToggleUng} aria-label={openUng ? "Đóng chi tiết ứng lương" : "Mở chi tiết ứng lương"}>{openUng ? "▾" : "▸"}</button>
      </div>
      {openUng && <EntryPanel entries={advances} showDate addPlaceholder="Số tiền ứng"
        submitLabel="Ghi ứng" notePlaceholder="VD: ứng mua xe…" noteSuggestions={UNG_GOI_Y}
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
