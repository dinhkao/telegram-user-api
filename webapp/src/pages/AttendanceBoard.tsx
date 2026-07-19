// DASHBOARD CHẤM CÔNG (#/cham-cong) — CHỈ văn phòng. Punch từ máy Ronald Jack theo
// tháng: mỗi (ngày, NV) 1 dòng giờ ĐẦU–CUỐI + số lần; bấm dòng xổ chi tiết từng lần.
// Khu "Mã chưa gán": employee_code trên máy chưa map → chọn thợ ngay tại chỗ.
// API: getAttendanceSummary/listAttendance/mapAttendanceCode. Gán ID cũng làm được ở
// chi tiết thợ (#/sx-tho/:name — ô "ID chấm công").
import { useEffect, useState } from "preact/hooks";
import {
  getAttendanceSummary, isOffice, listAttendance, listWorkers, mapAttendanceCode,
  type AttendanceDay, type AttendanceEvent, type AttendanceUnmapped, type Worker,
} from "../api";
import { dayLabel } from "../format";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { SelectPopup } from "../ui/SelectPopup";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { toast } from "../ui/feedback";

const pad = (n: number) => String(n).padStart(2, "0");
const curYM = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; };
const shiftYM = (ym: string, d: number) => { const [y, m] = ym.split("-").map(Number); const dt = new Date(y, m - 1 + d, 1); return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}`; };
const ymLabel = (ym: string) => { const [y, m] = ym.split("-"); return `Tháng ${Number(m)}/${y}`; };
const hhmm = (iso: string) => (iso && iso.length >= 16 ? iso.slice(11, 16) : "—");
const dmyt = (iso: string) => (iso && iso.length >= 16 ? `${Number(iso.slice(8, 10))}/${Number(iso.slice(5, 7))} ${iso.slice(11, 16)}` : "—");

function UnmappedCard({ u, workers, onDone }: { u: AttendanceUnmapped; workers: Worker[]; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const assign = async (v: string) => {
    const wid = Number(v);
    if (!wid || busy) return;
    setBusy(true);
    try {
      const r = await mapAttendanceCode(u.employee_code, wid);
      toast(`Đã gán mã ${u.employee_code} → ${workers.find((w) => w.id === wid)?.name || wid} (${r.updated_events} lần chấm)`, "ok");
      onDone();
    } catch (e: any) {
      toast(e?.message || "Lỗi gán mã", "err");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div class="att-unmapped-row">
      <span class="att-code">Mã {u.employee_code}</span>
      <span class="muted small">{u.punches} lần · gần nhất {dmyt(u.last)}</span>
      <SelectPopup value={null} searchable title={`Mã ${u.employee_code} là ai?`} placeholder="Gán thợ…"
        options={workers.map((w) => ({ value: w.id, label: w.name }))}
        onChange={assign} disabled={busy} />
    </div>
  );
}

function DayRow({ r }: { r: AttendanceDay }) {
  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState<AttendanceEvent[] | null>(null);
  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && events === null && r.punches > 2)
      listAttendance(r.day, r.employee_code).then(setEvents).catch(() => setEvents([]));
  };
  return (
    <div class="att-row-wrap">
      <button class="att-row" onClick={toggle}>
        {r.worker_name
          ? <span class="att-name">{r.worker_name}</span>
          : <span class="att-name att-code" title="Mã máy chưa gán thợ">Mã {r.employee_code}</span>}
        <span class="att-times">
          {hhmm(r.first)}{r.punches > 1 ? <> → {hhmm(r.last)}</> : null}
        </span>
        <span class="chip-n" title="Số lần chấm trong ngày">{r.punches}</span>
      </button>
      {open && r.punches > 2 && (
        events === null ? <div class="muted small att-detail">Đang tải…</div> : (
          <div class="att-detail muted small">
            {[...events].reverse().map((e) => hhmm(e.occurred_at)).join(" · ")}
          </div>
        )
      )}
    </div>
  );
}

export function AttendanceBoard() {
  const [ym, setYm] = useState(curYM());
  const [days, setDays] = useState<AttendanceDay[] | null>(null);
  const [unmapped, setUnmapped] = useState<AttendanceUnmapped[]>([]);
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [err, setErr] = useState("");

  const load = () => {
    setErr("");
    getAttendanceSummary(ym)
      .then((d) => { setDays(d.days); setUnmapped(d.unmapped); })
      .catch((e: any) => setErr(e?.message || "Lỗi tải chấm công"));
  };
  useEffect(() => { setDays(null); load(); }, [ym]);
  useEffect(() => { listWorkers().then(({ workers }) => setWorkers(workers)).catch(() => {}); }, []);

  if (!isOffice()) return <EmptyState icon="🔒">Chỉ văn phòng xem được chấm công.</EmptyState>;

  // Gộp theo ngày, mới nhất trước (server đã sort DESC theo ngày)
  const groups: { day: string; rows: AttendanceDay[] }[] = [];
  for (const r of days || []) {
    let g = groups.find((x) => x.day === r.day);
    if (!g) { g = { day: r.day, rows: [] }; groups.push(g); }
    g.rows.push(r);
  }

  return (
    <div class="prod-detail">
      <PageHead fallback="#/home" title={<><Icon name="clock" size={20} /> Chấm công</>}
        sub="Máy chấm công Ronald Jack — cập nhật 30 phút/lần" />

      <div class="seg att-month-nav">
        <button class="seg-btn" onClick={() => setYm(shiftYM(ym, -1))}>‹</button>
        <span class="att-month">{ymLabel(ym)}</span>
        <button class="seg-btn" onClick={() => setYm(shiftYM(ym, 1))} disabled={ym >= curYM()}>›</button>
      </div>

      {unmapped.length > 0 && (
        <section class="card">
          <label class="card-label t-warn"><Icon name="users" size={16} /> Mã máy chưa gán thợ ({unmapped.length})</label>
          <div class="muted small" style={{ marginBottom: 8 }}>
            Chấm công của các mã này chưa tính cho ai — chọn thợ để gán (áp cả lịch sử cũ).
          </div>
          {unmapped.map((u) => <UnmappedCard key={u.employee_code} u={u} workers={workers} onDone={load} />)}
        </section>
      )}

      {days === null && !err ? (
        <Loading />
      ) : err ? (
        <ErrorState msg={err} onRetry={load} />
      ) : !groups.length ? (
        <EmptyState icon="🕐">Chưa có chấm công tháng này.</EmptyState>
      ) : (
        groups.map((g) => (
          <section class="card" key={g.day}>
            <div class="row space">
              <label class="card-label" style={{ margin: 0 }}><Icon name="calendar" size={16} /> {dayLabel(g.day)}</label>
              <span class="muted small">{g.rows.length} người</span>
            </div>
            {g.rows.map((r) => <DayRow key={g.day + r.employee_code} r={r} />)}
          </section>
        ))
      )}
    </div>
  );
}
