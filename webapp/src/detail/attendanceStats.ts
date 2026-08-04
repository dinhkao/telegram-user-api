// Quy giờ chấm 1 ngày → (phút công, phút tăng ca) — GƯƠNG của
// attendance_store/domain.work_stats (2 ca 7–11/13–17, ngày đủ 480ph; cặp chấm
// liên tiếp = khoảng có mặt, lần lẻ bỏ; TC sau 11h/17h quá 15ph grace; khoảng
// xuyên trọn giờ trưa = nghi quên chấm → 11–13h không tính TC; ĐI LÀM CHỦ NHẬT =
// TĂNG CA TOÀN BỘ, không có ngày công).
// ⚠ ĐỔI LUẬT thì đổi CẢ 2 (server domain.work_stats + file này), không thì số công
// trên app lệch số công tính lương. Dùng ở: pages/WorkerAttendance (chấm công 1 thợ)
// và detail/PayrollCellPopup (ô Công/TC bảng lương).
const WIN: [number, number][] = [[7 * 60, 11 * 60], [13 * 60, 17 * 60]];
const GRACE = 15;
const mins = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));

/** 'YYYY-MM-DD' có phải CHỦ NHẬT không (chuỗi hỏng → false, không dám đoán). */
export function isSunday(ymd?: string): boolean {
  if (!ymd || !/^\d{4}-\d{2}-\d{2}$/.test(ymd)) return false;
  return new Date(`${ymd}T00:00:00`).getDay() === 0;
}

export function workStats(times: string[], ymd?: string): { work: number; ot: number } {
  const ts = times.map(mins).sort((a, b) => a - b);
  const spans: [number, number][] = [];
  for (let i = 0; i + 1 < ts.length; i += 2) if (ts[i + 1] > ts[i]) spans.push([ts[i], ts[i + 1]]);
  // ĐI LÀM CHỦ NHẬT = TĂNG CA TOÀN BỘ, không sinh ngày công nào
  if (isSunday(ymd)) return { work: 0, ot: spans.reduce((n, [s, e]) => n + Math.min(e, 24 * 60) - s, 0) };
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

/** Số công (ngày đủ 2 ca = 1) và giờ tăng ca của 1 ngày. */
export const dayCong = (times: string[], ymd?: string) => workStats(times, ymd).work / 480;
export const dayOtGio = (times: string[], ymd?: string) => workStats(times, ymd).ot / 60;
