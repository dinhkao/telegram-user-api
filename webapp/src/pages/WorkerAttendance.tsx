// CHẤM CÔNG 1 THỢ TRONG 1 THÁNG (#/cham-cong/:worker_id?ym=YYYY-MM) — mọi người
// dùng XEM được (không có số tiền nào ở đây); SỬA giờ = văn phòng, qua popup ngày
// dùng chung detail/AttendanceCellEditor (server cũng chặn).
// Vào từ: bảng lương tháng (ô Công/TC, hồ sơ lương thợ) và bảng chấm công cả xưởng.
// Dòng từng ngày + số công/TC = detail/AttendanceDays (DÙNG CHUNG với khối "Chấm công"
// trong hồ sơ lương thợ — sửa hiển thị thì sửa ở đó, đừng chép lại).
// API: getAttendanceSummary (lọc theo thợ) + listWorkers (tên, khi tháng chưa có giờ).
import { useEffect, useState } from "preact/hooks";
import { getAttendanceSummary, isOffice, listWorkers, type AttendanceDay, type Worker } from "../api";
import { curYM, shiftYM, ymLabel } from "../format";
import { AttendanceDayRows, attRows, attTotals, congVN } from "../detail/AttendanceDays";
import { CellEditor } from "../detail/AttendanceCellEditor";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { Loading, EmptyState, ErrorState } from "../ui/states";

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
    getAttendanceSummary(ym).then((s) => setDays(s.days))
      .catch((e: any) => { setErr(e?.message || "Lỗi tải chấm công"); setDays([]); });
  };
  useEffect(() => { setDays(null); load(); }, [ym, wid]);
  useEffect(() => { listWorkers().then(({ workers }) => setWorkers(workers)).catch(() => {}); }, []);

  const mine = (days || []).filter((d) => d.worker_id === wid);
  const name = mine.find((d) => d.worker_name)?.worker_name
    || workers.find((w) => w.id === wid)?.name || `#${wid}`;
  const code = mine.find((d) => d.employee_code)?.employee_code || "";
  const rows = attRows(days, wid);
  const tot = attTotals(rows);

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
              <div><span>Ngày công</span><b>{congVN(tot.cong)}</b></div>
              <div><span>Tăng ca</span><b class={tot.ot ? "t-warn" : ""}>{congVN(tot.ot)} giờ</b></div>
              <div><span>Ngày có chấm</span><b>{tot.ngay}</b></div>
            </section>
            {tot.le > 0 && (
              <p class="wa-warn small">
                ⚠ {tot.le} ngày chấm LẺ giờ (thiếu lượt vào hoặc ra) — giờ lẻ KHÔNG được tính công.
                {office ? " Bấm vào ngày đó để thêm giờ tay." : " Báo văn phòng để thêm giờ tay."}
              </p>
            )}
            {!rows.length ? (
              <EmptyState icon="🕐">Tháng này {name} chưa có giờ chấm nào.</EmptyState>
            ) : (
              <section class="card wa-list">
                <AttendanceDayRows rows={rows} onDay={code ? setEditDay : undefined} />
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
