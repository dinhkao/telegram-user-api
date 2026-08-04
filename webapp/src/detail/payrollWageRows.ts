// Gộp dòng báo cáo SX của 1 thợ thành các hình cần cho hồ sơ lương tháng
// (detail/PayrollWorkerSheet). Tách khỏi file đó vì file chạm trần 400 dòng khi mọi
// khối thành gập được; ở đây là logic THUẦN nên cũng dễ kiểm hơn.
import { soVN, type WorkerReport } from "../api";
import { pad2 } from "../format";

/** Số cây: có dấu chấm nghìn, bỏ đuôi ,00 (3420 → "3.420"; 12,5 → "12,5"). */
export const cayVN = (n: number) => soVN(Math.round((n || 0) * 100) / 100);
export const monthFrom = (ym: string) => `${ym}-01`;
export const monthTo = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  return `${ym}-${pad2(new Date(y, m, 0).getDate())}`;
};

/** CHI TIẾT: mỗi NGÀY có những PHIẾU SX nào, mỗi phiếu bao nhiêu cây / bao nhiêu tiền.
 *  (Thay cho view "theo mã SP" cũ — xem lương thì cái cần biết là phiếu nào ra tiền
 *  nào, còn tổng theo mã SP đã có ở trang sản xuất của thợ.) */
export function byDaySlip(rep: WorkerReport | null) {
  const days = new Map<string, { ymd: string; money: number; cay: number;
    slips: Map<number, { tid: number; codes: Set<string>; cay: number; money: number }> }>();
  for (const row of rep?.rows || []) {
    const ymd = row.ymd || "";
    const d = days.get(ymd) || { ymd, money: 0, cay: 0, slips: new Map() };
    d.cay += row.tong_calc || 0;
    d.money += row.money || 0;
    const sl = d.slips.get(row.thread_id)
      || { tid: row.thread_id, codes: new Set<string>(), cay: 0, money: 0 };
    if (row.product_code) sl.codes.add(row.product_code);
    sl.cay += row.tong_calc || 0;
    sl.money += row.money || 0;
    d.slips.set(row.thread_id, sl);
    days.set(ymd, d);
  }
  return [...days.values()]
    .sort((a, b) => a.ymd.localeCompare(b.ymd))
    .map((d) => ({ ...d, slips: [...d.slips.values()].sort((a, b) => b.money - a.money) }));
}

/** Gộp dòng báo cáo SX theo NGÀY (report_ymd) — xem lương SP rơi vào ngày nào. */
export function byDay(rep: WorkerReport | null) {
  const m = new Map<string, { ymd: string; cay: number; money: number; codes: Set<string>; phieu: Set<number> }>();
  for (const row of rep?.rows || []) {
    const ymd = row.ymd || "";
    const it = m.get(ymd) || { ymd, cay: 0, money: 0, codes: new Set<string>(), phieu: new Set<number>() };
    it.cay += row.tong_calc || 0;
    it.money += row.money || 0;
    if (row.product_code) it.codes.add(row.product_code);
    it.phieu.add(row.thread_id);
    m.set(ymd, it);
  }
  return [...m.values()].sort((a, b) => a.ymd.localeCompare(b.ymd));   // đầu tháng → cuối tháng
}


