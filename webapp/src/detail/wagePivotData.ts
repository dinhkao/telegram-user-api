// Tính toán THUẦN cho popup chi tiết ô bảng pivot lương SP (detail/WagePivotCell):
// tách tiền 1 ô thành 3 phần SP / TĂNG CA / PHỤ CẤP, gom theo ngày, đọc giờ phiếu.
// Không gọi API — chỉ đọc lại dữ liệu GET /api/production/wage-pivot đã tải.
// ⚠ phụ cấp phiếu đã được compute_range_report GỘP vào tiền ô, không có trường
// riêng → phụ cấp = tiền ô − tiền SP − tăng ca (xem production_store/wage_pivot.py).
import type { WagePivot, WagePivotDay, WagePivotSlip } from "../api";

export type Comp = { sp: number; tc: number; pc: number; total: number };
export const ZERO: Comp = { sp: 0, tc: 0, pc: 0, total: 0 };
export const addComp = (a: Comp, b: Comp): Comp =>
  ({ sp: a.sp + b.sp, tc: a.tc + b.tc, pc: a.pc + b.pc, total: a.total + b.total });

/** Cấu thành tiền của 1 thợ trong 1 phiếu. */
export function slipComp(s: WagePivotSlip, wid: number): Comp {
  const w = String(wid);
  const total = s.cells[w] || 0;
  let sp = 0, tc = 0;
  for (const p of s.parts?.[w] || []) {
    sp += p.gio > 0 ? Math.round(p.gio * p.rate) : Math.round(p.cay * p.wage);
    tc += p.ot || 0;
  }
  const pc = total - sp - tc;
  return { sp, tc, pc: Math.abs(pc) < 1 ? 0 : pc, total };
}

/** Cấu thành tiền của 1 thợ trong cả 1 ngày (cộng mọi phiếu). */
export const dayComp = (d: WagePivotDay, wid: number): Comp =>
  d.slips.reduce((acc, s) => addComp(acc, slipComp(s, wid)), ZERO);

/** Cấu thành tiền cả xưởng 1 ngày. */
export const dayTotalComp = (d: WagePivotDay, data: WagePivot): Comp =>
  data.workers.reduce((acc, w) => addComp(acc, dayComp(d, w.id)), ZERO);

/** Cấu thành cả 1 phiếu (mọi thợ). */
export const slipTotalComp = (s: WagePivotSlip, data: WagePivot): Comp =>
  data.workers.reduce((acc, w) => addComp(acc, slipComp(s, w.id)), ZERO);

/** Phiếu trong ngày có dính tới thợ này (có tiền, có cây hoặc có ghi chú). */
export const slipsOf = (d: WagePivotDay, wid: number) => {
  const w = String(wid);
  return d.slips.filter((s) => s.cells[w] || s.cay?.[w] || s.notes?.[w]);
};

/** "HH:MM" → phút trong ngày; sai/thiếu → null. */
export function tmin(t?: string): number | null {
  const m = String(t || "").match(/^(\d{1,2}):(\d{2})$/);
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}
/** Số phút của phiếu (0 nếu thiếu giờ / giờ xong ≤ giờ bắt đầu). */
export function slipMinutes(s: { start: string; end: string }): number {
  const a = tmin(s.start), b = tmin(s.end);
  return a != null && b != null && b > a ? b - a : 0;
}
/** 225 → "3 giờ 45 phút" · 45 → "45 phút" · 120 → "2 giờ". */
export function fmtDur(min: number): string {
  if (min <= 0) return "";
  const h = Math.floor(min / 60), m = min % 60;
  return h ? `${h} giờ${m ? ` ${m} phút` : ""}` : `${m} phút`;
}
/** "07:45" → "7:45". */
export const hm = (t?: string) => (t || "").replace(/^0(\d)/, "$1");

const DOW_FULL = ["Chủ nhật", "Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7"];
export const isSunday = (ymd: string) => new Date(`${ymd}T00:00:00`).getDay() === 0;
/** "2026-09-21" → "Thứ 2, 21/09/2026". */
export const dateLabel = (ymd: string) =>
  `${DOW_FULL[new Date(`${ymd}T00:00:00`).getDay()]}, ${ymd.slice(8, 10)}/${ymd.slice(5, 7)}/${ymd.slice(0, 4)}`;

/** Số lẻ kiểu VN: 12.5 → "12,5". */
export const soVN = (n: number) => String(Math.round(n * 10) / 10).replace(".", ",");

/** Nhãn loại ghi chú lệch chuẩn (khớp production_store/note_review.py KIND_*). */
export const FLAG_LABEL: Record<string, string> = {
  so_tien: "ghi chú có số tiền viết tay",
  mot_phan: "ghi chú thừa chữ so với câu chuẩn",
  la: "ghi chú lạ, không có trong quy tắc",
  khac_tho: "việc có phụ cấp nhưng của thợ khác",
};

/** Dấu ⚠ của 1 ô: "" = không · "open" = cần xem (chưa xử lý) · "done" = đã xử lý. */
export type FlagState = "" | "open" | "done";
export function slipFlag(s: WagePivotSlip, wid: number): FlagState {
  const f = s.flag?.[String(wid)];
  return !f ? "" : f.done ? "done" : "open";
}
/** Ô NGÀY: còn phiếu nào chưa xử lý → open; có mà đã xử lý hết → done. */
export function dayFlag(d: WagePivotDay, wid: number): FlagState {
  let st: FlagState = "";
  for (const s of d.slips) {
    const f = slipFlag(s, wid);
    if (f === "open") return "open";
    if (f === "done") st = "done";
  }
  return st;
}
