// CHẤM CÔNG 1 THỢ TRONG 1 THÁNG (#/cham-cong/:worker_id?ym=YYYY-MM) — mọi người
// dùng XEM được (không có số tiền nào ở đây); SỬA giờ = văn phòng, qua popup ngày
// dùng chung detail/AttendanceCellEditor (server cũng chặn).
// Vào từ: bảng lương tháng (ô Công/TC, hồ sơ lương thợ) và bảng chấm công cả xưởng.
// Số CÔNG/TĂNG CA tính bằng detail/attendanceStats.workStats = ĐÚNG luật server dùng
// để tính lương → số trên trang này khớp cột Công/TC của bảng lương.
// API: getAttendanceSummary (lọc theo thợ) + listWorkers (tên, khi tháng chưa có giờ).
import { useEffect, useState } from "preact/hooks";
import {
  getAttendanceSummary, isOffice, listWorkers,
  type AttendanceDay, type Worker,
} from "../api";
import { curYM, shiftYM, ymLabel } from "../format";
import { workStats } from "../detail/attendanceStats";
import { CellEditor } from "../detail/AttendanceCellEditor";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { Loading, EmptyState, ErrorState } from "../ui/states";

const DOW = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
const congVN = (n: number) => String(Math.round(n * 100) / 100).replace(".", ",");
const dowOf = (ymd: string) => new Date(`${ymd}T00:00:00`).getDay();
const dayVN = (ymd: string) => `${DOW[dowOf(ymd)]} ${Number(ymd.slice(8, 10))}/${Number(ymd.slice(5, 7))}`;
const queryYM = () => {
  const q = new URLSearchParams(window.location.hash.split("?")[1] || "").get("ym") || "";
  return /^\d{4}-\d{2}$/.test(q) ? q : curYM();
};

export function WorkerAttendance({ wid }: { wid: number }) {
  const [ym, setYmState] = useState(queryYM);
  const [days, setDays] = useState<AttendanceDay[] | null>(null);
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [err, setErr] = useState("");
  const [editDay, setEditDay] = useState<string | null>(null);
  const office = isOffice();

  const setYm = (next: string) => {
    setYmState(next);
    const base = window.location.hash.split("?")[0];
    history.replaceState(null, "", `${base}?ym=${encodeURIComponent(next)}`);
  };
  const load = () => {
    setErr("");
    getAttendanceSummary(ym)
      .then((s) => setDays(s.days.filter((d) => d.worker_id === wid).sort((a, b) => a.day.localeCompare(b.day))))
      .catch((e: any) => { setErr(e?.message || "Lỗi tải chấm công"); setDays([]); });
  };
  useEffect(() => { setDays(null); load(); }, [ym, wid]);
  useEffect(() => { listWorkers().then(({ workers }) => setWorkers(workers)).catch(() => {}); }, []);

  const name = days?.find((d) => d.worker_name)?.worker_name
    || workers.find((w) => w.id === wid)?.name || `#${wid}`;
  const code = days?.find((d) => d.employee_code)?.employee_code || "";

  const rows = (days || []).map((d) => {
    const st = workStats(d.times || []);
    return { ...d, cong: st.work / 480, ot: st.ot / 60, le: (d.times || []).length % 2 === 1 };
  }).filter((r) => (r.times || []).length > 0);
  const tongCong = rows.reduce((s, r) => s + r.cong, 0);
  const tongOt = rows.reduce((s, r) => s + r.ot, 0);
  const soLe = rows.filter((r) => r.le).length;

  const head = (
    <PageHead fallback="#/cham-cong"
      title={<><Icon name="clock" size={18} /> {name}</>}
      sub={`chấm công ${ymLabel(ym).toLowerCase()}${code ? ` · mã máy ${code}` : ""}`} />
  );

  return (
    <div class="pr-page wa-page">
      {head}
      <div class="pr-monthbar">
        <button class="pr-mnav" onClick={() => setYm(shiftYM(ym, -1))} aria-label="Tháng trước">‹</button>
        <b>{ymLabel(ym)}</b>
        <button class="pr-mnav" onClick={() => setYm(shiftYM(ym, 1))} aria-label="Tháng sau">›</button>
      </div>

      {err && !days?.length ? <ErrorState msg={err} onRetry={load} />
        : days === null ? <Loading />
        : (
          <>
            <section class="card wa-sum">
              <div><span>Ngày công</span><b>{congVN(tongCong)}</b></div>
              <div><span>Tăng ca</span><b class={tongOt ? "t-warn" : ""}>{congVN(tongOt)} giờ</b></div>
              <div><span>Ngày có chấm</span><b>{rows.length}</b></div>
            </section>
            {soLe > 0 && (
              <p class="wa-warn small">
                ⚠ {soLe} ngày chấm LẺ giờ (thiếu lượt vào hoặc ra) — giờ lẻ KHÔNG được tính công.
                {office ? " Bấm vào ngày đó để thêm giờ tay." : " Báo văn phòng để thêm giờ tay."}
              </p>
            )}
            {!rows.length ? (
              <EmptyState icon="🕐">Tháng này {name} chưa có giờ chấm nào.</EmptyState>
            ) : (
              <section class="card wa-list">
                {rows.map((r) => (
                  <button class={`wa-row${dowOf(r.day) === 0 ? " sun" : ""}`} key={r.day}
                    onClick={() => setEditDay(r.day)} title={office ? "Bấm để xem/sửa giờ ngày này" : "Bấm để xem giờ ngày này"}>
                    <span class="wa-day">{dayVN(r.day)}{r.edited ? " ✏️" : ""}</span>
                    <span class="wa-times">{(r.times || []).join(" · ")}
                      {r.le ? <span class="t-danger"> · lẻ giờ</span> : null}</span>
                    <b class={r.cong ? "" : "muted"}>{congVN(r.cong)} công</b>
                    <b class={r.ot ? "t-warn" : "muted"}>{r.ot ? `${congVN(r.ot)}g TC` : "—"}</b>
                  </button>
                ))}
              </section>
            )}
            <div class="wa-links">
              <a class="btn" href="#/cham-cong">🕐 Bảng chấm công cả xưởng</a>
              {office ? <a class="btn" href={`#/luong-thang/${wid}?ym=${encodeURIComponent(ym)}`}>💰 Lương tháng</a> : null}
            </div>
          </>
        )}

      {editDay && code && (
        <CellEditor code={code} who={name} day={editDay} canEdit={office}
          onClose={() => setEditDay(null)} onChanged={load} />
      )}
    </div>
  );
}
