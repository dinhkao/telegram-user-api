// LUẬT CHẤM CÔNG 1 NGÀY (thuần, không UI) — dùng bởi pages/AttendanceBoard.tsx.
// CHUẨN: 1 ngày ĐÚNG 4 lần chấm (vào-ra ca sáng + vào-ra ca chiều). Nhiều hơn hoặc
// ít hơn 4 = LỖI. Ngoại lệ DUY NHẤT: đúng 2 lần và cả 2 rơi vào CÙNG 1 buổi = làm
// nửa ngày (hợp lệ). 2 lần ở 2 buổi khác nhau (vd 7:00 & 17:00) = quên chấm ra sáng
// + vào chiều → LỖI. Không chấm lần nào = nghỉ, KHÔNG phải lỗi.
// ⚠ MIRROR của attendance_store/domain.py (day_error/day_warnings/day_issues — bản
// server dùng cho ảnh báo cáo hôm nay). Sửa 1 bên PHẢI sửa cả 2. Test: tests/attendanceRules.test.ts
export const STANDARD_PUNCHES = 4;
const NOON = 12 * 60;
const SHORT_PAIR_MIN = 30;              // cặp vào-ra < 30ph trong 1 ca = nghi bấm 2 lần liền
const SHIFT_WINDOWS: [number, number][] = [[7 * 60, 11 * 60], [13 * 60, 17 * 60]];

export type IssueLevel = "err" | "warn";
export type DayIssue = { level: IssueLevel; text: string };

export const attMins = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
const hhmm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
export const sessionOf = (t: string): "sang" | "chieu" => (attMins(t) < NOON ? "sang" : "chieu");

/** Cặp chấm liên tiếp (vào→ra) = các khoảng có mặt; lần chấm LẺ cuối bị bỏ. */
export function attPairs(times: string[]): [number, number][] {
  const ts = times.map(attMins).sort((a, b) => a - b);
  const out: [number, number][] = [];
  for (let i = 0; i + 1 < ts.length; i += 2) if (ts[i + 1] > ts[i]) out.push([ts[i], ts[i + 1]]);
  return out;
}

/** LỖI số lần chấm của 1 ngày (chuỗi hiện cho người dùng) hoặc null nếu đạt chuẩn. */
export function dayError(times: string[]): string | null {
  const ts = [...times].sort();
  const n = ts.length;
  if (n === 0 || n === STANDARD_PUNCHES) return null;
  if (n === 2) {
    if (sessionOf(ts[0]) === sessionOf(ts[1])) return null;   // làm 1 buổi: đủ cặp vào-ra
    return `chấm 2 lần ở 2 buổi khác nhau (${ts[0]} sáng, ${ts[1]} chiều)`
      + ` — thiếu chấm ra buổi sáng và chấm vào buổi chiều`;
  }
  if (n < STANDARD_PUNCHES) return `chỉ chấm ${n} lần — thiếu ${STANDARD_PUNCHES - n} lần (chuẩn ${STANDARD_PUNCHES} lần/ngày)`;
  return `chấm ${n} lần — nhiều hơn chuẩn ${STANDARD_PUNCHES} lần/ngày`;
}

/** Dấu hiệu đáng soi NGOÀI luật số lần: cặp vào-ra quá gần, cặp xuyên trọn giờ trưa. */
export function dayWarnings(times: string[]): string[] {
  const out: string[] = [];
  for (const [s, e] of attPairs(times)) {
    for (const [a, b] of SHIFT_WINDOWS) {
      if (s >= a && e <= b && e - s < SHORT_PAIR_MIN) {
        out.push(`${a < NOON ? "ca sáng" : "ca chiều"} chỉ có mặt ${e - s}ph (${hhmm(s)}→${hhmm(e)}) — nghi bấm 2 lần liền, thiếu chấm ra`);
      }
    }
    if (s <= SHIFT_WINDOWS[0][1] && e >= SHIFT_WINDOWS[1][0]) {
      out.push(`${hhmm(s)}→${hhmm(e)} xuyên trưa không chấm giữa — nghi quên chấm trưa (11–13h không tính tăng ca)`);
    }
  }
  return out;
}

/** Mọi vấn đề của 1 ngày. Sai chuẩn số lần → CHỈ trả lỗi đó (khỏi báo trùng). */
export function dayIssues(times: string[]): DayIssue[] {
  const err = dayError(times);
  if (err) return [{ level: "err", text: err }];
  return dayWarnings(times).map((text): DayIssue => ({ level: "warn", text }));
}
