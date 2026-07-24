// POPUP Ô BẢNG LƯƠNG THÁNG — bấm 1 ô trong bảng (#/luong-thang) mở popup xem/thao
// tác đúng nội dung ô đó: Công/TC = chấm công từng ngày của thợ (luật quy công
// GIỐNG attendance_store/domain.work_stats); L.công/L.TC/Lương/Lãnh = diễn giải
// công thức; P.cấp/Ứng = panel thêm/vô hiệu khoản ngay tại chỗ (EntryPanel).
// Data: getAttendanceSummary, payroll allowance/advance API. Cha (MonthlyPayroll)
// giữ state {wid, col} và truyền row TƯƠI mỗi lần data đổi.
import { useEffect, useState } from "preact/hooks";
import {
  addPayrollAdvance, addPayrollAllowance, getAttendanceSummary,
  listPayrollAdvances, listPayrollAllowances, soVN,
  voidPayrollAdvance, voidPayrollAllowance,
  type AttendanceDay, type PayrollMonth, type PayrollRow,
  type SalaryAdvance, type SalaryAllowance,
} from "../api";
import { Icon } from "../ui/Icon";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";
import { LoadingInline } from "../ui/states";
import { toast, promptDialog } from "../ui/feedback";

export type PayrollCol = "name" | "cong" | "tc" | "luong_cong" | "luong_tc" | "luong" | "pc" | "ung" | "net";

import { moneyR as money } from "../format";
const num = (s: string) => Number(String(s).replace(/[^\d]/g, "") || 0);
const congVN = (n: number) => String(Math.round(n * 100) / 100).replace(".", ",");

// ── Quy giờ chấm 1 ngày → (phút công, phút tăng ca) — GƯƠNG của
// attendance_store/domain.work_stats (2 ca 7–11/13–17, ngày đủ 480ph; cặp chấm
// liên tiếp = khoảng có mặt, lần lẻ bỏ; TC sau 11h/17h quá 15ph grace; khoảng
// xuyên trọn giờ trưa = nghi quên chấm → 11–13h không tính TC).
const WIN: [number, number][] = [[7 * 60, 11 * 60], [13 * 60, 17 * 60]];
const GRACE = 15;
const mins = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
export function workStats(times: string[]): { work: number; ot: number } {
  const ts = times.map(mins).sort((a, b) => a - b);
  const spans: [number, number][] = [];
  for (let i = 0; i + 1 < ts.length; i += 2) if (ts[i + 1] > ts[i]) spans.push([ts[i], ts[i + 1]]);
  let work = 0, ot = 0;
  const [, mEnd] = WIN[0];
  const [aStart, aEnd] = WIN[1];
  for (const [s, e] of spans) {
    for (const [a, b] of WIN) work += Math.max(0, Math.min(e, b) - Math.max(s, a));
    const lunch = s <= mEnd && e >= aStart;
    if (!lunch && s <= mEnd && e > mEnd) {
      const seg = Math.min(e, aStart) - mEnd;
      if (seg > GRACE) ot += seg;
    }
    if (e > aEnd + GRACE) ot += Math.min(e, 24 * 60) - aEnd;
  }
  return { work, ot };
}

const DOW = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
const dayVN = (ymd: string) => {
  const d = new Date(`${ymd}T00:00:00`);
  return `${DOW[d.getDay()]} ${Number(ymd.slice(8, 10))}/${Number(ymd.slice(5, 7))}`;
};

// Panel liệt kê + thêm/VÔ HIỆU KHOẢN (phụ cấp lẫn ứng — chuyển từ MonthlyPayroll
// sang đây để popup + thẻ dùng chung). Khoản vô hiệu vẫn hiện (gạch + ai/lý do).
export function EntryPanel({ entries, showDate, addPlaceholder, onAdd, onDel, extra }: {
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

const TITLES: Record<PayrollCol, string> = {
  name: "Nhân viên", cong: "Ngày công", tc: "Giờ tăng ca",
  luong_cong: "Lương theo công", luong_tc: "Lương tăng ca", luong: "Lương",
  pc: "Phụ cấp", ung: "Ứng lương", net: "Thực lãnh",
};

export function PayrollCellPopup({ ym, r, col, onClose, onCol, apply, editMoc, toggleType, toggleWeekly }: {
  ym: string; r: PayrollRow; col: PayrollCol;
  onClose: () => void; onCol: (c: PayrollCol) => void;
  apply: (d: PayrollMonth) => void;
  editMoc: (r: PayrollRow) => void;
  toggleType: (r: PayrollRow) => void; toggleWeekly: (r: PayrollRow) => void;
}) {
  usePopupBack(true, onClose);
  useScrollLock(true);
  const wid = r.worker_id;
  const isTime = r.wage_type === "time";
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
              <b class={hl === "work" ? "" : "muted"}>{congVN(st.work / 480)} công</b>
              <b class={hl === "ot" ? "t-warn" : "muted"}>{st.ot ? `${congVN(st.ot / 60)}g TC` : "—"}</b>
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

        {col === "name" && (
          <>
            <Row label="Loại lương" val={<button class={isTime ? "chip pr-type time" : "chip pr-type"} onClick={() => toggleType(r)}>{isTime ? "Thời gian" : "Sản phẩm"}</button>} />
            <Row label="Nhận lương tuần (tháng này)" val={
              <span class={r.weekly ? "tgl on" : "tgl"} role="switch" aria-checked={r.weekly} onClick={() => toggleWeekly(r)}><span class="tgl-knob" /></span>} />
            {isTime && <Row label="Mốc lương tháng" val={<button class="pr-ung-btn" onClick={() => editMoc(r)}>{r.monthly_salary ? `${money(r.monthly_salary)}đ` : "đặt…"}</button>} />}
            <a class="btn block" href={`#/sx-tho/${encodeURIComponent(r.name)}`}>🏭 Chi tiết thợ (sản xuất)</a>
            <a class="btn block" href="#/cham-cong">🕐 Bảng chấm công</a>
          </>
        )}

        {(col === "cong" || col === "tc") && (
          <>
            <div class="pr-pop-sum">
              <Row label="Tổng công (ngày đủ 2 ca = 1)" val={congVN(r.cong)} cls={col === "cong" ? "hl" : ""} />
              <Row label="Tổng tăng ca" val={`${congVN(r.ot_gio)} giờ`} cls={col === "tc" ? "hl" : ""} />
            </div>
            {attList(col === "cong" ? "work" : "ot")}
            <a class="btn block" href="#/cham-cong">🕐 Mở bảng chấm công (sửa giờ tay)</a>
          </>
        )}

        {col === "luong_cong" && (
          <>
            {isTime ? (
              <>
                <Row label="Mốc lương tháng" val={<button class="pr-ung-btn" onClick={() => editMoc(r)}>{r.monthly_salary ? `${money(r.monthly_salary)}đ` : "đặt…"}</button>} />
                <Row label="Lương 1 công (mốc ÷ 26)" val={`${money(dayRate)}đ`} />
                <Row label="Ngày công" val={congVN(r.cong)} go="cong" />
                <Row label={<b>Lương công = {money(dayRate)} × {congVN(r.cong)}</b>} val={`${money(r.luong_cong)}đ`} cls="hl" />
              </>
            ) : <p class="muted small">{r.name} hưởng lương SẢN PHẨM — không tính lương theo công.</p>}
          </>
        )}

        {col === "luong_tc" && (
          <>
            {isTime ? (
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
              <Row label="Lương theo công" val={`${money(r.luong_cong)}đ`} go="luong_cong" />
              <Row label="Lương tăng ca (×1,2)" val={`${money(r.luong_tc)}đ`} go="luong_tc" />
              <Row label={<b>Lương thời gian</b>} val={`${money(r.luong)}đ`} cls="hl" />
            </>
          ) : (
            <>
              <Row label="Lương sản phẩm (tự tính từ báo cáo SX)" val={`${money(r.luong)}đ`} cls="hl" />
              <p class="muted small">= tổng cây × đơn giá chốt theo từng phiếu SX trong tháng (+ phụ cấp phiếu).</p>
              <a class="btn block" href={`#/sx-tho/${encodeURIComponent(r.name)}`}>🏭 Chi tiết sản xuất của thợ</a>
              <a class="btn block" href="#/bao-cao">📄 Phiếu báo cáo SX</a>
            </>
          )
        )}

        {col === "pc" && (
          <>
            <EntryPanel entries={allows} addPlaceholder="Số tiền phụ cấp"
              onAdd={(a, note) => addAllow(a, note)} onDel={voidAllow} />
            <a class="btn block" href={`#/nhap-phu-cap?ym=${encodeURIComponent(ym)}&worker_id=${wid}`}>📋 Trang nhập phụ cấp</a>
          </>
        )}

        {col === "ung" && (
          <>
            <EntryPanel entries={advs} showDate addPlaceholder="Số tiền ứng"
              onAdd={(a, note, date) => addAdv(a, note, date)} onDel={voidAdv}
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
            {r.thuong ? <Row label="Thưởng (tháng cũ)" val={`+${money(r.thuong)}đ`} /> : null}
            <Row label={`Đã ứng${r.adv_count ? ` (${r.adv_count} lần)` : ""}`} val={`−${money(r.ung)}đ`} go="ung" />
            <Row label={<b>Thực lãnh</b>} val={`${money(r.thuc_lanh)}đ`} cls={r.thuc_lanh < 0 ? "hl t-danger" : "hl"} />
          </>
        )}

        <button class="btn sh-cancel" onClick={onClose}>Đóng</button>
      </div>
    </div>
  );
}
