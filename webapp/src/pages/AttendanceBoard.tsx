// DASHBOARD CHẤM CÔNG (#/cham-cong) — CHỈ văn phòng. LƯỚI COMPACT cả tháng:
// cột đầu CỐ ĐỊNH (sticky) = tên NV (+ tổng TĂNG CA tháng, tím); mỗi NGÀY 1 cột gồm
// 3 ỐNG dọc = ca SÁNG 7–11 + ca CHIỀU 13–17 + TĂNG CA 🌙 17–21 (tím, mảnh hơn).
// Mô hình: cặp chấm liên tiếp (vào→ra, vào→ra…) = các KHOẢNG CÓ MẶT trong ngày; mỗi
// ống tô những đoạn giao giữa khoảng có mặt và khung giờ của ống → đủ ca = ống đầy,
// làm xuyên trưa/về muộn đều hiện đúng chỗ. Chấm LẺ cuối ngày (thiếu vào/ra) = vạch
// cam. Tăng ca đếm = có mặt NGOÀI 2 khung ca (trước 7h, 11–13, sau 17h; bỏ đoạn <10
// phút khỏi nhiễu) — tổng tháng hiện cạnh tên. Kéo NGANG xem hết tháng, CN nền hồng,
// hôm nay viền; bấm 1 ống → toast giờ chấm chi tiết. Banner: cập nhật gần nhất
// (last_sync) + lần kế ≈ +30ph. Khu "Mã chưa gán": chọn thợ ngay tại chỗ.
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
const hgm = (m: number) => (m % 60 === 0 ? `${m / 60}g` : `${Math.floor(m / 60)}g${pad(m % 60)}`);

// 3 khung giờ hiển thị: 2 ca chính + khung tăng ca chiều tối (tím).
const SHIFTS = [
  { key: "sang", label: "Ca sáng", from: 7 * 60, to: 11 * 60, ot: false },
  { key: "chieu", label: "Ca chiều", from: 13 * 60, to: 17 * 60, ot: false },
  { key: "tc", label: "Tăng ca", from: 17 * 60, to: 21 * 60, ot: true },
];
// Tăng ca THẬT = có mặt ngoài 2 khung ca chính; đoạn < 10 phút bỏ (nhiễu chấm sớm/muộn vài phút)
const WORK_WINDOWS: [number, number][] = [[7 * 60, 11 * 60], [13 * 60, 17 * 60]];
const OT_MIN_SEG = 10;

type Interval = [number, number];
// Cặp chấm liên tiếp → các khoảng có mặt; lẻ → dư 1 điểm cuối (thiếu vào/ra)
function presence(times: string[]): { spans: Interval[]; loose: number | null } {
  const ts = times.map(mins);
  const spans: Interval[] = [];
  for (let i = 0; i + 1 < ts.length; i += 2) if (ts[i + 1] > ts[i]) spans.push([ts[i], ts[i + 1]]);
  return { spans, loose: ts.length % 2 ? ts[ts.length - 1] : null };
}
const clip = (spans: Interval[], a: number, b: number): Interval[] =>
  spans.map(([s, e]): Interval => [Math.max(s, a), Math.min(e, b)]).filter(([s, e]) => e > s);
// Khoảng phủ TRỌN giờ trưa (vào ≤11h, ra ≥13h) không chấm giữa = nghi QUÊN chấm trưa
const LUNCH: Interval = [11 * 60, 13 * 60];
const crossesLunch = ([s, e]: Interval) => s <= LUNCH[0] && e >= LUNCH[1];

// Phút tăng ca trong ngày: có mặt trừ phần nằm trong 2 khung ca chính. Đoạn xuyên
// TRỌN giờ trưa không tính 11–13 là TC (nghi quên chấm trưa — xem detectIssues).
function otMinutes(spans: Interval[]): number {
  let total = 0;
  for (const [s, e] of spans) {
    let out = e - s;
    for (const [a, b] of WORK_WINDOWS) out -= Math.max(0, Math.min(e, b) - Math.max(s, a));
    if (crossesLunch([s, e])) out -= LUNCH[1] - LUNCH[0];
    if (out >= OT_MIN_SEG) total += out;
  }
  return total;
}

// ── Nhận diện CHẤM THIẾU (heuristic thuần, chạy trên times 1 ngày) ──────────
const SHORT_PAIR_MIN = 30;   // cặp vào-ra < 30ph nằm gọn trong 1 ca = nghi bấm 2 lần liền
const tstr = (m: number) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
function detectIssues(times: string[]): string[] {
  const { spans, loose } = presence(times);
  const issues: string[] = [];
  if (loose !== null) {
    const shift = loose < 12 * 60 ? "ca sáng" : loose < 17 * 60 ? "ca chiều" : "tăng ca";
    issues.push(`chấm ${times.length} lần (lẻ) — ${shift} thiếu 1 lần vào/ra (lần lẻ lúc ${tstr(loose)})`);
  }
  for (const [s, e] of spans) {
    for (const [a, b] of WORK_WINDOWS) {
      if (s >= a && e <= b && e - s < SHORT_PAIR_MIN) {
        issues.push(`${a < 12 * 60 ? "ca sáng" : "ca chiều"} chỉ có mặt ${e - s}ph (${tstr(s)}→${tstr(e)}) — nghi bấm 2 lần liền, thiếu chấm ra`);
      }
    }
    if (crossesLunch([s, e]) ) {
      issues.push(`${tstr(s)}→${tstr(e)} xuyên trưa không chấm giữa — nghi quên chấm trưa (11–13h không tính tăng ca)`);
    }
  }
  return issues;
}

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

// 1 ỐNG = 1 khung giờ: tô các đoạn có mặt giao với khung; vạch cam = chấm lẻ trong khung.
function Tube({ spans, loose, shift, allTimes, dayLbl, who }: {
  spans: Interval[]; loose: number | null; shift: typeof SHIFTS[0];
  allTimes: string[]; dayLbl: string; who: string;
}) {
  const dur = shift.to - shift.from;
  const segs = clip(spans, shift.from, shift.to);
  // chấm LẺ thuộc đúng 1 ống: <12h = sáng, 12–17h = chiều, ≥17h = tăng ca
  const belongs = loose !== null && (
    shift.key === "sang" ? loose < 12 * 60 :
    shift.key === "chieu" ? loose >= 12 * 60 && loose < 17 * 60 : loose >= 17 * 60);
  const mark = belongs && loose !== null ? Math.min(Math.max(loose, shift.from), shift.to) : null;
  const empty = !segs.length && mark === null;
  const show = () => {
    if (!allTimes.length) return;
    toast(`${who} · ${dayLbl}: ${allTimes.join(" → ")}${allTimes.length % 2 ? " (thiếu 1 lần chấm)" : ""}`,
      allTimes.length % 2 ? "err" : "ok");
  };
  return (
    <span class={"att-tube" + (shift.ot ? " ot" : "") + (mark !== null ? " one" : "")} onClick={show}
      title={empty ? `${shift.label}: trống` : shift.label}>
      {segs.map(([s, e], i) => (
        <span key={i} class={"att-fill" + (shift.ot ? " ot" : "")}
          style={{ top: `${((s - shift.from) / dur) * 100}%`, height: `${Math.max(((e - s) / dur) * 100, 6)}%` }} />
      ))}
      {mark !== null && <span class="att-mark" style={{ top: `calc(${((mark - shift.from) / dur) * 100}% - 1px)` }} />}
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

  // Ma trận NV × ngày: rows theo tên (mapped trước, mã lạ sau); mỗi ô = times[] gộp
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
  const rows = [...people.values()]
    .map((p) => {
      let ot = 0;
      for (const times of p.byDay.values()) ot += otMinutes(presence(times).spans);
      return { ...p, ot };
    })
    .sort((a, b) => (a.mapped !== b.mapped ? (a.mapped ? -1 : 1) : a.label.localeCompare(b.label, "vi")));
  const dayNums = Array.from({ length: nDays }, (_, i) => i + 1);
  const isSun = (d: number) => new Date(Y, M - 1, d).getDay() === 0;

  // Quét CHẤM THIẾU toàn tháng: mỗi (ngày, NV) chạy detectIssues, mới nhất trước
  const suspects: { d: number; who: string; texts: string[] }[] = [];
  for (const p of rows) {
    for (const [d, times] of p.byDay) {
      const texts = detectIssues(times);
      if (texts.length) suspects.push({ d, who: p.label, texts });
    }
  }
  suspects.sort((a, b) => b.d - a.d || a.who.localeCompare(b.who, "vi"));

  return (
    <div class="prod-detail">
      <PageHead fallback="#/home" title={<><Icon name="clock" size={20} /> Chấm công</>}
        sub="3 ống/ngày: ☀ 7–11 · ⛅ 13–17 · 🌙 tăng ca 17–21 (tím). Xanh = có mặt, vạch cam = thiếu chấm. Kéo ngang xem cả tháng." />
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

      {suspects.length > 0 && (
        <details class="card att-issues" open={suspects.length <= 6}>
          <summary class="card-label t-warn">
            <span>⚠</span> Nghi chấm thiếu ({suspects.length})
          </summary>
          <div class="muted small" style={{ margin: "4px 0 8px" }}>
            Máy ghi gì tính nấy — các ca dưới đây có dấu hiệu THIẾU lần chấm, nhắc nhân viên
            chấm đủ vào/ra từng buổi.
          </div>
          {suspects.map((s, i) => (
            <div class="att-issue-row" key={i}>
              <span class="att-issue-day">{s.d}/{M}</span>
              <span class="att-issue-who">{s.who}</span>
              <span class="att-issue-txt">{s.texts.map((t, j) => <div key={j}>• {t}</div>)}</span>
            </div>
          ))}
        </details>
      )}

      {days === null && !err ? (
        <Loading />
      ) : err ? (
        <ErrorState msg={err} onRetry={load} />
      ) : !rows.length ? (
        <EmptyState icon="🕐">Chưa có chấm công tháng này.</EmptyState>
      ) : (
        <div class="card att-grid-card">
          <div class="att-grid" style={{ gridTemplateColumns: `minmax(76px, auto) repeat(${nDays}, 33px)` }}>
            <div class="att-g-corner" />
            {dayNums.map((d) => (
              <div class={"att-g-day" + (isSun(d) ? " sun" : "") + (d === todayD ? " today" : "")} key={`h${d}`}>{d}</div>
            ))}
            {rows.map((p, ri) => (
              <>
                <div class={"att-g-name" + (p.mapped ? "" : " att-code") + (ri % 2 ? " alt" : "")} key={`n${ri}`}
                  title={p.ot > 0 ? `Tăng ca tháng này: ${hgm(p.ot)}` : undefined}>
                  <span class="att-g-nm">{p.label}</span>
                  {p.ot > 0 && <span class="att-ot-total">TC {hgm(p.ot)}</span>}
                </div>
                {dayNums.map((d) => {
                  const times = p.byDay.get(d) || [];
                  const { spans, loose } = presence(times);
                  const dayLbl = `${d}/${M}`;
                  return (
                    <div class={"att-g-cell" + (isSun(d) ? " sun" : "") + (d === todayD ? " today" : "") + (ri % 2 ? " alt" : "")} key={`${ri}-${d}`}>
                      {SHIFTS.map((sh) => (
                        <Tube key={sh.key} spans={spans} loose={loose} shift={sh}
                          allTimes={times} dayLbl={dayLbl} who={p.label} />
                      ))}
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
