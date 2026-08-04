// DÒNG CHẤM CÔNG THEO NGÀY — dùng chung: trang chấm công 1 thợ
// (pages/WorkerAttendance) và khối "Chấm công" trong hồ sơ lương tháng
// (detail/PayrollWorkerSheet). 1 dòng = 1 ngày: thứ+ngày · mọi giờ chấm · số công ·
// giờ tăng ca; CN nền hồng, ✏️ = ngày có sửa tay, "lẻ giờ" = thiếu lượt vào/ra.
// Số công/TC lấy từ attendanceStats.workStats (gương luật server tính lương).
// ⚠ Sửa cách hiển thị ngày công thì sửa Ở ĐÂY để 2 nơi không lệch nhau.
import { type AttendanceDay } from "../api";
import { workStats } from "./attendanceStats";

const DOW = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
export const congVN = (n: number) => String(Math.round(n * 100) / 100).replace(".", ",");
/** Giờ tăng ca trên DÒNG NGÀY: 1 chữ số thập phân cho ngắn (tổng tháng vẫn để 2 số). */
export const otVN = (n: number) => String(Math.round(n * 10) / 10).replace(".", ",");
export const dowOf = (ymd: string) => new Date(`${ymd}T00:00:00`).getDay();
export const dayVN = (ymd: string) => `${DOW[dowOf(ymd)]} ${Number(ymd.slice(8, 10))}/${Number(ymd.slice(5, 7))}`;

export type AttRow = AttendanceDay & { cong: number; ot: number; le: boolean };

/** Ngày CÓ chấm giờ của 1 thợ (đã tính công/TC), sắp đầu tháng → cuối tháng. */
export function attRows(days: AttendanceDay[] | null, wid: number): AttRow[] {
  return (days || [])
    .filter((d) => d.worker_id === wid && (d.times || []).length > 0)
    .sort((a, b) => a.day.localeCompare(b.day))
    .map((d) => {
      const st = workStats(d.times || [], d.day);
      return { ...d, cong: st.work / 480, ot: st.ot / 60, le: (d.times || []).length % 2 === 1 };
    });
}

/** Tổng tháng: công, giờ tăng ca, số ngày có chấm, số ngày lẻ giờ. */
export function attTotals(rows: AttRow[]) {
  return {
    cong: rows.reduce((s, r) => s + r.cong, 0),
    ot: rows.reduce((s, r) => s + r.ot, 0),
    ngay: rows.length,
    le: rows.filter((r) => r.le).length,
  };
}

/** Ghép giờ chấm thành CẶP vào–ra (2 lần chấm = 1 lượt có mặt). Lượt cuối thiếu
 *  giờ ra → b = null (hiện "?" đỏ). Ghép cặp cho ngắn: "06:58–11:03 · 12:58–17:12"
 *  gọn hơn hẳn 4 mốc rời và đọc ra ngay ca sáng/ca chiều. */
export function pairs(times: string[]): [string, string | null][] {
  const out: [string, string | null][] = [];
  for (let i = 0; i < times.length; i += 2) out.push([times[i], times[i + 1] ?? null]);
  return out;
}

export function AttendanceDayRows({ rows, onDay }: {
  rows: AttRow[];
  onDay?: (day: string) => void;   // bấm 1 ngày → popup giờ (chỉ trang chấm công)
}) {
  return (
    <>
      {rows.map((r) => {
        const inner = (
          <>
            <span class="wa-day">{dayVN(r.day)}{r.edited ? <span class="wa-ed" title="có sửa giờ tay">✏️</span> : null}</span>
            <span class="wa-times">
              {pairs(r.times || []).map(([a, b], i) => (
                <span class="wa-pair" key={i}>{a}<span class="wa-dash">–</span>{b || <b class="t-danger" title="thiếu lượt ra">?</b>}</span>
              ))}
            </span>
            <span class="wa-nums">
              <b class={r.cong >= 1 ? "" : r.cong ? "t-warn" : "muted"}>{congVN(r.cong)}<small> công</small></b>
              {/* tăng ca: 1 chữ số thập phân + bỏ chữ "TC" cho vừa 1 dòng máy hẹp
                  (cột này chỉ có công & tăng ca nên không lẫn được) */}
              {r.ot ? <b class="t-warn wa-ot" title="giờ tăng ca">+{otVN(r.ot)}<small>g</small></b> : null}
            </span>
          </>
        );
        const cls = `wa-row${dowOf(r.day) === 0 ? " sun" : ""}${r.le ? " le" : ""}`;
        return onDay
          ? <button class={cls} key={r.day} onClick={() => onDay(r.day)} title="Bấm để xem/sửa giờ ngày này">{inner}</button>
          : <div class={cls} key={r.day}>{inner}</div>;
      })}
    </>
  );
}
