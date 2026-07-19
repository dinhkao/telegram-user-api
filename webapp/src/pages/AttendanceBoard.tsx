// DASHBOARD CHẤM CÔNG (#/cham-cong) — CHỈ văn phòng. LƯỚI COMPACT cả tháng:
// cột đầu CỐ ĐỊNH (sticky) = tên NV; mỗi NGÀY 1 cột gồm 2 ỐNG dọc = ca SÁNG 7–11 +
// ca CHIỀU 13–17. Ống là micro-timeline: đoạn xanh = khoảng có mặt (chấm vào→ra, kẹp
// vào khung ca) — chấm đủ ca = ống đầy; 1 lần chấm (thiếu vào/ra) = vạch cam; trống =
// ống trắng. Kéo NGANG xem hết tháng, chủ nhật nền hồng, hôm nay viền đậm; bấm 1 ống
// → toast giờ chấm chi tiết. Banner: cập nhật gần nhất (last_sync) + lần kế ≈ +30ph.
// Khu "Mã chưa gán": employee_code trên máy chưa map → chọn thợ ngay tại chỗ.
// API: getAttendanceSummary/mapAttendanceCode. Gán ID cũng ở chi tiết thợ (#/sx-tho).
import { useEffect, useState } from "preact/hooks";
import {
  getAttendanceSummary, isOffice, listWorkers, mapAttendanceCode,
  type AttendanceDay, type AttendanceUnmapped, type Worker,
} from "../api";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { SelectPopup } from "../ui/SelectPopup";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { toast } from "../ui/feedback";

const pad = (n: number) => String(n).padStart(2, "0");
const curYM = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; };
const shiftYM = (ym: string, d: number) => { const [y, m] = ym.split("-").map(Number); const dt = new Date(y, m - 1 + d, 1); return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}`; };
const ymLabel = (ym: string) => { const [y, m] = ym.split("-"); return `Tháng ${Number(m)}/${y}`; };
const dmyt = (iso: string) => (iso && iso.length >= 16 ? `${Number(iso.slice(8, 10))}/${Number(iso.slice(5, 7))} ${iso.slice(11, 16)}` : "—");
const mins = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));

// 2 ca cố định: sáng 7–11, chiều 13–17 (mốc chia 12:00). Chấm sớm/muộn hơn khung vẫn
// tính — kẹp vào mép ống.
const SHIFTS = [
  { key: "sang", label: "Ca sáng", from: 7 * 60, to: 11 * 60 },
  { key: "chieu", label: "Ca chiều", from: 13 * 60, to: 17 * 60 },
];
const SPLIT = 12 * 60;

function SyncBanner({ lastSync, intervalMin }: { lastSync: string | null; intervalMin: number }) {
  // received_at = 'YYYY-MM-DD HH:MM:SS' giờ VN (server cùng múi giờ người dùng)
  if (!lastSync) return null;
  const last = new Date(lastSync.replace(" ", "T"));
  if (isNaN(last.getTime())) return null;
  const next = new Date(last.getTime() + intervalMin * 60000);
  const overdue = Date.now() > next.getTime() + 5 * 60000;   // trễ >5ph = máy chưa gửi
  const hm = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const sameDay = last.toDateString() === new Date().toDateString();
  return (
    <div class="att-sync muted small">
      <Icon name="clock" size={13} /> Cập nhật {sameDay ? hm(last) : dmyt(lastSync.replace(" ", "T"))}
      {" · "}
      {overdue
        ? <span class="t-warn">lần kế {hm(next)} đã quá giờ — đang chờ máy gửi</span>
        : <>lần kế ≈ <b>{hm(next)}</b></>}
    </div>
  );
}

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

// 1 ỐNG = 1 ca: đoạn xanh từ giờ VÀO → RA (kẹp trong khung ca); 1 lần chấm = vạch cam.
function Tube({ times, shift, dayLbl, who }: { times: string[]; shift: typeof SHIFTS[0]; dayLbl: string; who: string }) {
  const dur = shift.to - shift.from;
  let seg: { top: number; h: number; kind: "ok" | "one" } | null = null;
  if (times.length >= 2) {
    const a = Math.max(mins(times[0]), shift.from);
    const b = Math.min(mins(times[times.length - 1]), shift.to);
    if (b > a) seg = { top: (a - shift.from) / dur, h: (b - a) / dur, kind: "ok" };
  } else if (times.length === 1) {
    const p = Math.min(Math.max(mins(times[0]), shift.from), shift.to);
    seg = { top: (p - shift.from) / dur, h: 0, kind: "one" };
  }
  const show = () => {
    if (!times.length) return;
    toast(`${who} · ${dayLbl} ${shift.label}: ${times.join(" → ")}${times.length === 1 ? " (thiếu 1 lần chấm)" : ""}`, times.length === 1 ? "err" : "ok");
  };
  return (
    <span class={"att-tube" + (times.length === 1 ? " one" : "")} onClick={show}>
      {seg && seg.kind === "ok" && (
        <span class="att-fill" style={{ top: `${seg.top * 100}%`, height: `${Math.max(seg.h * 100, 6)}%` }} />
      )}
      {seg && seg.kind === "one" && (
        <span class="att-mark" style={{ top: `calc(${seg.top * 100}% - 1px)` }} />
      )}
    </span>
  );
}

export function AttendanceBoard() {
  const [ym, setYm] = useState(curYM());
  const [days, setDays] = useState<AttendanceDay[] | null>(null);
  const [unmapped, setUnmapped] = useState<AttendanceUnmapped[]>([]);
  const [sync, setSync] = useState<{ last: string | null; interval: number }>({ last: null, interval: 30 });
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [err, setErr] = useState("");

  const load = () => {
    setErr("");
    getAttendanceSummary(ym)
      .then((d) => { setDays(d.days); setUnmapped(d.unmapped); setSync({ last: d.last_sync, interval: d.sync_interval_min }); })
      .catch((e: any) => setErr(e?.message || "Lỗi tải chấm công"));
  };
  useEffect(() => { setDays(null); load(); }, [ym]);
  useEffect(() => { listWorkers().then(({ workers }) => setWorkers(workers)).catch(() => {}); }, []);

  if (!isOffice()) return <EmptyState icon="🔒">Chỉ văn phòng xem được chấm công.</EmptyState>;

  // Ma trận NV × ngày: rows theo tên (mapped trước, mã lạ sau), mỗi ô = times[]
  const [Y, M] = ym.split("-").map(Number);
  const nDays = new Date(Y, M, 0).getDate();
  const today = new Date();
  const todayD = today.getFullYear() === Y && today.getMonth() + 1 === M ? today.getDate() : 0;
  const people = new Map<string, { label: string; mapped: boolean; byDay: Map<number, string[]> }>();
  for (const r of days || []) {
    const key = r.worker_id != null ? `w${r.worker_id}` : `c${r.employee_code}`;
    let p = people.get(key);
    if (!p) {
      p = { label: r.worker_name || `Mã ${r.employee_code}`, mapped: r.worker_id != null, byDay: new Map() };
      people.set(key, p);
    }
    const d = Number(r.day.slice(8, 10));
    p.byDay.set(d, [...(p.byDay.get(d) || []), ...(r.times || [])].sort());
  }
  const rows = [...people.values()].sort((a, b) =>
    a.mapped !== b.mapped ? (a.mapped ? -1 : 1) : a.label.localeCompare(b.label, "vi"));
  const dayNums = Array.from({ length: nDays }, (_, i) => i + 1);
  const isSun = (d: number) => new Date(Y, M - 1, d).getDay() === 0;

  return (
    <div class="prod-detail">
      <PageHead fallback="#/home" title={<><Icon name="clock" size={20} /> Chấm công</>}
        sub="Mỗi ngày 2 ống: ☀ 7–11 · ⛅ 13–17. Xanh = có mặt, đầy = đủ ca, vạch cam = thiếu chấm. Kéo ngang xem cả tháng." />
      <SyncBanner lastSync={sync.last} intervalMin={sync.interval} />

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
      ) : !rows.length ? (
        <EmptyState icon="🕐">Chưa có chấm công tháng này.</EmptyState>
      ) : (
        <div class="card att-grid-card">
          <div class="att-grid" style={{ gridTemplateColumns: `minmax(72px, auto) repeat(${nDays}, 27px)` }}>
            <div class="att-g-corner" />
            {dayNums.map((d) => (
              <div class={"att-g-day" + (isSun(d) ? " sun" : "") + (d === todayD ? " today" : "")} key={`h${d}`}>{d}</div>
            ))}
            {rows.map((p, ri) => (
              <>
                <div class={"att-g-name" + (p.mapped ? "" : " att-code") + (ri % 2 ? " alt" : "")} key={`n${ri}`}>{p.label}</div>
                {dayNums.map((d) => {
                  const times = p.byDay.get(d) || [];
                  const dayLbl = `${d}/${M}`;
                  return (
                    <div class={"att-g-cell" + (isSun(d) ? " sun" : "") + (d === todayD ? " today" : "") + (ri % 2 ? " alt" : "")} key={`${ri}-${d}`}>
                      <Tube times={times.filter((t) => mins(t) < SPLIT)} shift={SHIFTS[0]} dayLbl={dayLbl} who={p.label} />
                      <Tube times={times.filter((t) => mins(t) >= SPLIT)} shift={SHIFTS[1]} dayLbl={dayLbl} who={p.label} />
                    </div>
                  );
                })}
              </>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
