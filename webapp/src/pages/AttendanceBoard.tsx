// DASHBOARD CHẤM CÔNG (#/cham-cong) — MỌI người dùng XEM được; SỬA (gán mã,
// ẩn/thêm/xoá giờ) chỉ văn phòng (server cũng chặn). LƯỚI COMPACT cả tháng:
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
import { useEffect, useRef, useState } from "preact/hooks";
import {
  addAttendanceManual, deleteAttendanceManual, getAttendanceDay, getAttendanceSummary,
  isOffice, listWorkers, mapAttendanceCode, renderAttendanceTodayImage, suppressAttendance,
  type AttendanceDay, type AttendanceDayDetail, type AttendanceUnmapped, type Worker,
} from "../api";
import { dayLabel } from "../format";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { SelectPopup } from "../ui/SelectPopup";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";
import { Loading, LoadingInline, EmptyState, ErrorState } from "../ui/states";
import { toast, confirmDialog } from "../ui/feedback";

const pad = (n: number) => String(n).padStart(2, "0");
const NAME_W = 112;   // bề rộng CỐ ĐỊNH cột tên (px) — CHUNG cho header + thân lưới
                      // để ngày ở header luôn thẳng cột với ô dữ liệu (auto lệch nhau).
// Kích hoạt bằng bàn phím cho phần tử không phải <button> (Enter/Space).
const keyActivate = (fn: () => void) => (e: any) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fn(); }
};
const curYM = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; };
const shiftYM = (ym: string, d: number) => { const [y, m] = ym.split("-").map(Number); const dt = new Date(y, m - 1 + d, 1); return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}`; };
const ymLabel = (ym: string) => { const [y, m] = ym.split("-"); return `Tháng ${Number(m)}/${y}`; };
const dmyt = (iso: string) => (iso && iso.length >= 16 ? `${Number(iso.slice(8, 10))}/${Number(iso.slice(5, 7))} ${iso.slice(11, 16)}` : "—");
const mins = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
const todayISO = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };

// 3 khung giờ hiển thị: 2 ca chính + khung tăng ca chiều tối (tím).
const SHIFTS = [
  { key: "sang", label: "Ca sáng", from: 7 * 60, to: 11 * 60, ot: false },
  { key: "chieu", label: "Ca chiều", from: 13 * 60, to: 17 * 60, ot: false },
  { key: "tc", label: "Tăng ca", from: 17 * 60, to: 21 * 60, ot: true },
];
// Tăng ca THẬT = có mặt ngoài 2 khung ca chính; đoạn < 10 phút bỏ (nhiễu chấm sớm/muộn vài phút)
const WORK_WINDOWS: [number, number][] = [[7 * 60, 11 * 60], [13 * 60, 17 * 60]];
// Chấm ra ≤15ph sau hết ca (11:00/17:00) = về trễ lặt vặt, KHÔNG tính tăng ca
const OT_GRACE = 15;

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

function blobDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("Không đọc được ảnh"));
    reader.readAsDataURL(blob);
  });
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
  // 1 span chữ liền — không tách node kẻo flex-gap bẻ "·" rơi lẻ dòng
  return (
    <div class="att-sync muted small">
      <Icon name="clock" size={13} />
      <span>
        Cập nhật <b>{sameDay ? hm(last) : dmyt(lastSync.replace(" ", "T"))}</b>
        {" · "}
        {overdue
          // máy CHỈ gửi khi có chấm mới — quá lịch không đồng nghĩa hỏng, đừng báo động
          ? <>chưa có chấm mới từ đó (máy gửi 30ph/lần khi có người chấm)</>
          : <>lần kế ≈ <b>{hm(next)}</b></>}
      </span>
    </div>
  );
}

function UnmappedCard({ u, workers, onDone }: { u: AttendanceUnmapped; workers: Worker[]; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const assign = async (v: string) => {
    const wid = Number(v);
    if (!wid || busy) return;
    const name = workers.find((w) => w.id === wid)?.name || wid;
    if (!(await confirmDialog(`Gán mã ${u.employee_code} cho ${name}? Áp cho CẢ ${u.punches} lần chấm cũ.`, { okLabel: "Gán" }))) return;
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

// 1 ỐNG = 1 khung giờ: tô các đoạn có mặt giao với khung; vạch cam = chấm lẻ trong
// khung. Click xử lý ở Ô (mở popup sửa giờ) — ống không tự bắt sự kiện.
function Tube({ spans, loose, shift }: {
  spans: Interval[]; loose: number | null; shift: typeof SHIFTS[0];
}) {
  const dur = shift.to - shift.from;
  const segs = clip(spans, shift.from, shift.to);
  // chấm LẺ thuộc đúng 1 ống: <12h = sáng, 12–17h = chiều, ≥17h = tăng ca
  const belongs = loose !== null && (
    shift.key === "sang" ? loose < 12 * 60 :
    shift.key === "chieu" ? loose >= 12 * 60 && loose < 17 * 60 : loose >= 17 * 60);
  const mark = belongs && loose !== null ? Math.min(Math.max(loose, shift.from), shift.to) : null;
  // ống TC trống = mờ hẳn (ngày thường không tăng ca — đỡ rối lưới)
  const ghost = shift.ot && !segs.length && mark === null;
  return (
    <span class={"att-tube" + (shift.ot ? " ot" : "") + (mark !== null ? " one" : "") + (ghost ? " ghost" : "")} title={shift.label}>
      {segs.map(([s, e], i) => (
        <span key={i} class={"att-fill" + (shift.ot ? " ot" : "")}
          style={{ top: `${((s - shift.from) / dur) * 100}%`, height: `${Math.max(((e - s) / dur) * 100, 6)}%` }} />
      ))}
      {mark !== null && <span class="att-mark" style={{ top: `calc(${((mark - shift.from) / dur) * 100}% - 1px)` }} />}
    </span>
  );
}

// POPUP XEM/SỬA GIỜ 1 (NV, ngày) — neo đỉnh màn. Giờ MÁY chỉ Ẩn/Hiện (raw bất biến);
// sửa 1 giờ = ẩn giờ máy rồi thêm giờ tay. Mỗi thao tác ghi server ngay + reload.
// canEdit=false (staff): chỉ xem giờ, không nút sửa.
function CellEditor({ code, who, day, canEdit, onClose, onChanged }: {
  code: string; who: string; day: string; canEdit: boolean; onClose: () => void; onChanged: () => void;
}) {
  const [det, setDet] = useState<AttendanceDayDetail | null>(null);
  const [loadErr, setLoadErr] = useState(false);
  const [newTime, setNewTime] = useState("");
  const [busy, setBusy] = useState(false);
  useScrollLock(true);
  usePopupBack(true, onClose);
  // Lỗi tải KHÔNG được giả làm "rỗng" — người dùng sẽ tưởng chưa chấm mà sửa nhầm.
  const reload = () => { setLoadErr(false); return getAttendanceDay(code, day).then(setDet).catch(() => { setDet(null); setLoadErr(true); }); };
  useEffect(() => { reload(); }, [code, day]);

  const run = async (fn: () => Promise<any>, okMsg: string): Promise<boolean> => {
    if (busy) return false;
    setBusy(true);
    try {
      await fn();
      toast(okMsg, "ok");
      await reload();
      onChanged();
      return true;
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu", "err");
      return false;
    } finally {
      setBusy(false);
    }
  };
  const addTime = async () => {
    if (!newTime) return;
    // Chỉ xoá ô nhập KHI lưu thành công — hỏng thì giữ lại để khỏi gõ lại.
    if (await run(() => addAttendanceManual(code, day, newTime), `Đã thêm giờ ${newTime}`)) setNewTime("");
  };
  const [y, m, d] = day.split("-");
  return (
    <div class="att-ed-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="att-ed" role="dialog" aria-modal="true" aria-label={`${canEdit ? "Sửa" : "Xem"} giờ chấm — ${who}`}>
        <div class="att-ed-head">
          <b>{who}</b>
          <span class="muted">{Number(d)}/{Number(m)}/{y}</span>
          <button class="icon-btn att-ed-x" onClick={onClose} title="Đóng" aria-label="Đóng cửa sổ sửa chấm công">✕</button>
        </div>
        {loadErr ? <ErrorState msg="Không tải được giờ chấm ngày này" onRetry={reload} />
          : det === null ? <LoadingInline /> : (
          <>
            <div class="att-ed-sec">Giờ máy chấm {det.machine.length === 0 && <span class="muted small">— không có</span>}</div>
            {det.machine.map((mrow) => (
              <div class={"att-ed-row" + (mrow.suppressed ? " off" : "")} key={mrow.event_id}>
                <span class="att-ed-time">{mrow.time}</span>
                {mrow.suppressed && <span class="att-ed-badge">đã ẩn</span>}
                {canEdit && <button class="btn att-ed-btn" disabled={busy}
                  onClick={() => run(() => suppressAttendance(mrow.event_id, !mrow.suppressed),
                    mrow.suppressed ? `Đã hiện lại giờ ${mrow.time}` : `Đã ẩn giờ ${mrow.time}`)}>
                  {mrow.suppressed ? "Hiện lại" : "Ẩn"}
                </button>}
              </div>
            ))}
            <div class="att-ed-sec">Giờ thêm tay</div>
            {det.manual.map((mn) => (
              <div class="att-ed-row" key={mn.id}>
                <span class="att-ed-time">{mn.time}</span>
                <span class="muted small">✎ {mn.created_by || "?"}</span>
                {canEdit && <button class="btn att-ed-btn danger" disabled={busy}
                  onClick={async () => { if (await confirmDialog(`Xoá giờ thêm tay ${mn.time}?`, { danger: true })) run(() => deleteAttendanceManual(mn.id), `Đã xoá giờ ${mn.time}`); }}>Xoá</button>}
              </div>
            ))}
            {canEdit && <>
              <div class="att-ed-row att-ed-add">
                <input type="time" class="pw-input" value={newTime} disabled={busy}
                  onInput={(e: any) => setNewTime(e.target.value)} />
                <button class="btn att-ed-btn" disabled={busy || !newTime} onClick={addTime}>＋ Thêm giờ</button>
              </div>
              <div class="muted small att-ed-note">
                Giờ máy không sửa trực tiếp được — muốn sửa 1 giờ: bấm <b>Ẩn</b> giờ sai rồi
                <b> Thêm giờ</b> đúng. Dữ liệu máy giữ nguyên nên lần đồng bộ sau không đè phần sửa.
              </div>
            </>}
          </>
        )}
      </div>
    </div>
  );
}

// View DÒNG: 1 cụm giờ của 1 buổi — mọi lần chấm nối bằng →. Cảnh báo LẺ tính ở
// CẤP NGÀY (tổng lần chấm) chứ KHÔNG theo buổi: cắt buổi theo mốc giờ hay bẻ đôi
// cặp vào-ra (vd 13:00→20:00 tăng ca) nên đếm lẻ theo buổi sẽ báo động giả.
function ListShift({ icon, times }: { icon: string; times: string[] }) {
  return (
    <span class={"att-shift" + (times.length === 0 ? " empty" : "")}
      title={times.length === 0 ? "Không chấm" : `${times.length} lần chấm`}>
      <span class="att-shift-ico">{icon}</span>
      {times.length === 0 ? <span class="att-shift-none">—</span> : times.map((t, i) => (
        <span class="att-t" key={i}>{t}{i < times.length - 1 ? <span class="att-arrow">→</span> : null}</span>
      ))}
    </span>
  );
}

export function AttendanceBoard() {
  const office = isOffice();   // staff: chỉ XEM — ẩn gán mã + nút sửa giờ (server cũng chặn)
  const [ym, setYm] = useState(curYM());
  const [view, setViewRaw] = useState<"grid" | "list">(
    (localStorage.getItem("att_view") as "grid" | "list") || "grid");
  const setView = (v: "grid" | "list") => { setViewRaw(v); try { localStorage.setItem("att_view", v); } catch {} };
  const [days, setDays] = useState<AttendanceDay[] | null>(null);
  const [unmapped, setUnmapped] = useState<AttendanceUnmapped[]>([]);
  const [sync, setSync] = useState<{ last: string | null; interval: number }>({ last: null, interval: 30 });
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [err, setErr] = useState("");
  const [editor, setEditor] = useState<{ code: string; who: string; day: string } | null>(null);
  const [imageBusy, setImageBusy] = useState(false);
  const [reportImage, setReportImage] = useState<{ url: string; blob: Blob; name: string } | null>(null);
  const headRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const reqRef = useRef(0);

  const load = () => {
    setErr("");
    const my = ++reqRef.current;   // đổi tháng nhanh → response cũ về sau bị bỏ (chống race)
    getAttendanceSummary(ym)
      .then((d) => {
        if (my !== reqRef.current) return;
        setDays(d.days); setUnmapped(d.unmapped); setSync({ last: d.last_sync, interval: d.sync_interval_min });
      })
      .catch((e: any) => { if (my !== reqRef.current) return; setErr(e?.message || "Lỗi tải chấm công"); });
  };
  // Đổi tháng: xoá SẠCH dữ liệu tháng cũ (kể cả mã chưa gán + banner sync) trước khi tải.
  useEffect(() => { setDays(null); setUnmapped([]); setSync({ last: null, interval: 30 }); load(); }, [ym]);
  // Danh sách thợ chỉ phục vụ khu gán mã (office) — staff khỏi tải.
  useEffect(() => { if (!office) return; listWorkers().then(({ workers }) => setWorkers(workers)).catch(() => toast("Không tải được danh sách thợ — thử tải lại trang", "err")); }, []);
  useEffect(() => () => { if (reportImage) URL.revokeObjectURL(reportImage.url); }, [reportImage]);
  // Tháng hiện tại: cuộn lưới tới cột HÔM NAY (khỏi kéo ngang từ ngày 1), giữ cột tên sticky.
  useEffect(() => {
    const [Yv, Mv] = ym.split("-").map(Number);
    const now = new Date();
    const td = now.getFullYear() === Yv && now.getMonth() + 1 === Mv ? now.getDate() : 0;
    if (td && bodyRef.current) bodyRef.current.scrollLeft = Math.max(0, (td - 1) * 33 - 96);
  }, [days, ym]);

  // Ma trận NV × ngày: rows theo tên (mapped trước, mã lạ sau); mỗi ô = times[] gộp
  const [Y, M] = ym.split("-").map(Number);
  const nDays = new Date(Y, M, 0).getDate();
  const today = new Date();
  const todayD = today.getFullYear() === Y && today.getMonth() + 1 === M ? today.getDate() : 0;
  const people = new Map<string, {
    label: string; mapped: boolean; code: string;
    byDay: Map<number, string[]>; codeByDay: Map<number, string>; edDays: Set<number>;
  }>();
  for (const r of days || []) {
    const key = r.worker_id != null ? `w${r.worker_id}` : `c${r.employee_code}`;
    let p = people.get(key);
    if (!p) {
      p = { label: r.worker_name || `Mã ${r.employee_code}`, mapped: r.worker_id != null,
            code: r.employee_code, byDay: new Map(), codeByDay: new Map(), edDays: new Set() };
      people.set(key, p);
    }
    const d = Number(r.day.slice(8, 10));
    p.byDay.set(d, [...(p.byDay.get(d) || []), ...(r.times || [])].sort());
    if (!p.codeByDay.has(d)) p.codeByDay.set(d, r.employee_code);   // popup sửa đúng mã của ngày đó
    if (r.edited) p.edDays.add(d);
  }
  const rows = [...people.values()]
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

  const generateTodayImage = async () => {
    if (imageBusy || !days) return;
    setImageBusy(true);
    try {
      const day = todayISO();
      // Cho React kịp paint trạng thái loading trước khi chờ server render.
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      const blob = await renderAttendanceTodayImage();
      const name = `cham-cong-${day}.png`;
      setReportImage({ url: URL.createObjectURL(blob), blob, name });
      toast("Đã tạo ảnh chấm công hôm nay", "ok");
    } catch (e: any) {
      toast(e?.message || "Không tạo được ảnh chấm công", "err");
    } finally {
      setImageBusy(false);
    }
  };

  const saveReportImage = async () => {
    if (!reportImage) return;
    try {
      const bridge: any = (window as any).AndroidApp;
      if (bridge?.saveImage) {
        const ok = bridge.saveImage(await blobDataUrl(reportImage.blob), reportImage.name);
        toast(ok === false ? "Lưu ảnh lỗi" : "Đã lưu ảnh vào thư viện", ok === false ? "err" : "ok");
        return;
      }
      const nav: any = navigator;
      const file = new File([reportImage.blob], reportImage.name, { type: "image/png" });
      if (nav.canShare?.({ files: [file] })) {
        await nav.share({ files: [file], title: reportImage.name });
        return;
      }
      const a = document.createElement("a");
      a.href = reportImage.url;
      a.download = reportImage.name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      toast("Đã tải ảnh chấm công", "ok");
    } catch (e: any) {
      if (e?.name !== "AbortError") toast("Không lưu/chia sẻ được ảnh", "err");
    }
  };

  return (
    <div class="prod-detail">
      <PageHead fallback="#/home" title={<><Icon name="clock" size={20} /> Chấm công</>}
        sub={`☀ 7–11 · ⛅ 13–17 · 🌙 tăng ca. Xanh = có mặt, cam = thiếu chấm. Bấm ô để ${office ? "sửa" : "xem"} giờ.`} />
      <SyncBanner lastSync={sync.last} intervalMin={sync.interval} />

      <div class="att-toolbar">
        <div class="seg att-month-nav">
          <button class="seg-btn" onClick={() => setYm(shiftYM(ym, -1))}>‹</button>
          <span class="att-month">{ymLabel(ym)}</span>
          <button class="seg-btn" onClick={() => setYm(shiftYM(ym, 1))} disabled={ym >= curYM()}>›</button>
        </div>
        <div class="seg">
          <button class={view === "grid" ? "seg-btn active" : "seg-btn"} onClick={() => setView("grid")} title="Lưới cả tháng">▦ Lưới</button>
          <button class={view === "list" ? "seg-btn active" : "seg-btn"} onClick={() => setView("list")} title="Danh sách theo ngày">☰ Dòng</button>
        </div>
        <button class="btn primary att-export-btn" disabled={!days || imageBusy} onClick={generateTodayImage}>
          <Icon name="image" size={15} /> {imageBusy ? "Đang tạo ảnh…" : "Tạo ảnh hôm nay"}
        </button>
      </div>

      {office && unmapped.length > 0 && (
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
      ) : view === "list" ? (
        (() => {
          // View DÒNG: gộp theo ngày (server đã sort DESC), mỗi người 1 dòng đủ mọi giờ chấm
          const groups: { day: string; rows: AttendanceDay[] }[] = [];
          for (const r of days || []) {
            let g = groups.find((x) => x.day === r.day);
            if (!g) { g = { day: r.day, rows: [] }; groups.push(g); }
            g.rows.push(r);
          }
          return groups.map((g) => (
            <section class="card" key={g.day}>
              <div class="row space">
                <label class="card-label" style={{ margin: 0 }}><Icon name="calendar" size={16} /> {dayLabel(g.day)}</label>
                <span class="muted small">{g.rows.length} người</span>
              </div>
              {g.rows.map((r) => {
                const ts = r.times || [];
                const who = r.worker_name || `Mã ${r.employee_code}`;
                const open = () => setEditor({ code: r.employee_code, who, day: g.day });
                const dayOdd = ts.length % 2 === 1;   // tổng lần chấm LẺ = nghi thiếu 1 lần vào/ra
                // 🌙 chỉ tính khi chấm sau 17:00 + OT_GRACE (17:15) — GIỐNG ống tăng ca ở lưới;
                // chấm ra đúng/quanh 17:00 vẫn là ca chiều, không tách thành tăng ca.
                const OT_FROM = 17 * 60 + OT_GRACE;
                const hasOt = ts.some((t) => mins(t) >= OT_FROM);
                return (
                  <div class="att-lrow" key={g.day + r.employee_code} title={office ? "Bấm để xem / sửa giờ chấm" : "Bấm để xem giờ chấm"}
                    role="button" tabIndex={0} onKeyDown={keyActivate(open)}
                    aria-label={`${who} — ${ts.length ? `${ts.length} lần chấm, bấm để ${office ? "sửa" : "xem"}` : "chưa chấm"}`}
                    onClick={open}>
                    {r.worker_name
                      ? <span class="att-name">{r.worker_name}</span>
                      : <span class="att-name att-code" title="Mã máy chưa gán thợ">Mã {r.employee_code}</span>}
                    {r.edited && <span class="att-edited-mark" title="Có sửa tay">✎</span>}
                    <span class="att-shifts">
                      <ListShift icon="☀" times={ts.filter((t) => mins(t) < 12 * 60)} />
                      <ListShift icon="⛅" times={ts.filter((t) => mins(t) >= 12 * 60 && mins(t) < OT_FROM)} />
                      {hasOt && <ListShift icon="🌙" times={ts.filter((t) => mins(t) >= OT_FROM)} />}
                    </span>
                    {dayOdd && <span class="att-warn-mark" title="Tổng lần chấm trong ngày LẺ — nghi thiếu 1 lần vào/ra">⚠</span>}
                  </div>
                );
              })}
            </section>
          ));
        })()
      ) : (
        // Cuộn DỌC theo TRANG như bảng lương tháng: header ngày là thanh sticky
        // top:44 (dưới app-bar); thân lưới cuộn NGANG riêng, scrollLeft đồng bộ
        // sang header (header overflow:hidden — không tự cuộn được).
        <div class="card att-grid-card">
          <div class="att-ghead" ref={headRef}
            style={{ gridTemplateColumns: `${NAME_W}px repeat(${nDays}, 33px)` }}>
            <div class="att-g-corner" />
            {dayNums.map((d) => (
              <div class={"att-g-day" + (isSun(d) ? " sun" : "") + (d === todayD ? " today" : "")} key={`h${d}`}>{d}</div>
            ))}
          </div>
          <div class="att-grid" ref={bodyRef}
            onScroll={() => { if (headRef.current && bodyRef.current) headRef.current.scrollLeft = bodyRef.current.scrollLeft; }}
            style={{ gridTemplateColumns: `${NAME_W}px repeat(${nDays}, 33px)` }}>
            {rows.map((p, ri) => (
              <>
                <div class={"att-g-name" + (p.mapped ? "" : " att-code") + (ri % 2 ? " alt" : "")} key={`n${ri}`}>
                  <span class="att-g-nm">{p.label}</span>
                </div>
                {dayNums.map((d) => {
                  const times = p.byDay.get(d) || [];
                  const { spans, loose } = presence(times);
                  const open = () => setEditor({ code: p.codeByDay.get(d) || p.code, who: p.label, day: `${ym}-${pad(d)}` });
                  return (
                    <div key={`${ri}-${d}`} role="button" tabIndex={0} onKeyDown={keyActivate(open)}
                      class={"att-g-cell" + (isSun(d) ? " sun" : "") + (d === todayD ? " today" : "")
                        + (ri % 2 ? " alt" : "") + (p.edDays.has(d) ? " edited" : "")}
                      title={office ? "Bấm để xem / sửa giờ chấm" : "Bấm để xem giờ chấm"}
                      aria-label={`${p.label} ngày ${d}/${M} — ${times.length ? `${times.length} lần chấm, bấm để ${office ? "sửa" : "xem"}` : "chưa chấm"}`}
                      onClick={open}>
                      {SHIFTS.map((sh) => (
                        <Tube key={sh.key} shift={sh} loose={loose}
                          // ống TĂNG CA: chỉ tô khi chấm ra QUÁ giờ hết ca >15ph
                          spans={sh.ot ? spans.filter(([, e]) => e > sh.from + OT_GRACE) : spans} />
                      ))}
                    </div>
                  );
                })}
              </>
            ))}
          </div>
        </div>
      )}

      {editor && (
        <CellEditor code={editor.code} who={editor.who} day={editor.day} canEdit={office}
          onClose={() => setEditor(null)} onChanged={load} />
      )}
      {reportImage && (
        <div class="att-image-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) setReportImage(null); }}>
          <div class="att-image-sheet" role="dialog" aria-modal="true" aria-label="Ảnh chấm công hôm nay">
            <div class="att-image-head"><b>Ảnh chấm công hôm nay</b><button class="icon-btn" onClick={() => setReportImage(null)} title="Đóng">✕</button></div>
            <img src={reportImage.url} class="att-image-preview" alt="Bảng chấm công hôm nay" />
            <div class="att-image-actions">
              <button class="btn primary block" onClick={saveReportImage}><Icon name="download" size={15} /> Lưu / chia sẻ ảnh</button>
              <button class="btn block" onClick={() => setReportImage(null)}>Đóng</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
