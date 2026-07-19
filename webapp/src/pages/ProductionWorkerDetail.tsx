// Chi tiết 1 thợ (#/sx-tho/:name) — mỗi NGÀY làm những phiếu nào, SP gì, bao nhiêu SP.
// Gộp theo ngày (report_ymd), mỗi dòng link tới phiếu SX. Lọc kỳ giống dashboard.
// Office còn sửa được HỒ SƠ: đổi TÊN (bút chì cạnh tên — server cascade mirror rows +
// blob bang, xong điều hướng sang hash tên mới), NGÀY VÀO LÀM, GHI CHÚ, lương tuần,
// tiền 1 giờ, ID CHẤM CÔNG (mã NV trên máy Ronald Jack → map + backfill qua
// /api/attendance/map — xem dashboard #/cham-cong).
// API: getWorkerReport. Realtime production_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import {
  getWorkerReport, isOffice, listAttendanceMap, listWorkers, mapAttendanceCode, soVN,
  updateWorker, type Worker, type WorkerReport, type WorkerReportRow,
} from "../api";
import { onRealtime } from "../realtime";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";
import { toast, promptDialog } from "../ui/feedback";

const pad = (n: number) => String(n).padStart(2, "0");
const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const dmy = (ymd: string) => { if (!ymd) return "?"; const [y, m, d] = ymd.split("-"); return `${d}/${m}/${y}`; };
const money = (n: number) => soVN(Math.round(n)) + "đ";

type Period = "all" | "month" | "week";
function rangeFor(p: Period): { from?: string; to?: string } {
  if (p === "all") return {};
  const now = new Date();
  const to = iso(now);
  if (p === "month") return { from: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-01`, to };
  const wk = new Date(now); wk.setDate(now.getDate() - 6);
  return { from: iso(wk), to };
}

export function ProductionWorkerDetail({ name }: { name: string }) {
  const [period, setPeriod] = useState<Period>("month");
  const [data, setData] = useState<WorkerReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [worker, setWorker] = useState<Worker | null>(null);
  const [wkBusy, setWkBusy] = useState(false);

  // Tìm row thợ theo tên (để đọc/sửa cờ weekly_salary)
  useEffect(() => {
    listWorkers()
      .then(({ workers }) => setWorker(workers.find((w) => w.name.trim().toLowerCase() === name.trim().toLowerCase()) || null))
      .catch(() => {});
  }, [name]);

  const flipWeekly = async () => {
    if (!worker || wkBusy) return;
    setWkBusy(true);
    try {
      const w = await updateWorker(worker.id, { weekly_salary: !worker.weekly_salary });
      setWorker(w);
      toast(w.weekly_salary ? "Đã BẬT nhận lương tuần" : "Đã TẮT nhận lương tuần", "ok");
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu", "err");
    } finally {
      setWkBusy(false);
    }
  };

  // Tiền 1 GIỜ làm — cho SP tính lương THEO GIỜ (cột "Giờ" trong báo cáo thợ)
  const [rateDraft, setRateDraft] = useState<string | null>(null);
  const saveRate = async () => {
    if (!worker || rateDraft === null) return;
    const v = Number(rateDraft.replace(/[^\d]/g, "") || 0);
    setRateDraft(null);
    if (v === Math.round(worker.hourly_rate || 0)) return;
    try {
      const w = await updateWorker(worker.id, { hourly_rate: v });
      setWorker(w);
      toast(`Đã lưu tiền 1 giờ: ${money(v)}`, "ok");
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu tiền 1 giờ", "err");
    }
  };

  // ID CHẤM CÔNG — mã NV trên máy Ronald Jack gán cho thợ này (1 thợ có thể nhiều mã)
  const [attCodes, setAttCodes] = useState<string[]>([]);
  const [attDraft, setAttDraft] = useState("");
  const [attBusy, setAttBusy] = useState(false);
  const loadAttCodes = (wid: number) => {
    listAttendanceMap()
      .then((ms) => setAttCodes(ms.filter((m) => m.worker_id === wid).map((m) => m.employee_code)))
      .catch(() => {});
  };
  useEffect(() => { if (isOffice() && worker) loadAttCodes(worker.id); }, [worker?.id]);
  const addAttCode = async () => {
    const code = attDraft.trim();
    if (!worker || !code || attBusy) return;
    setAttBusy(true);
    try {
      const r = await mapAttendanceCode(code, worker.id);
      setAttDraft("");
      toast(`Đã gán ID chấm công ${code} (${r.updated_events} lần chấm cũ)`, "ok");
      loadAttCodes(worker.id);
    } catch (e: any) {
      toast(e?.message || "Lỗi gán ID chấm công", "err");
    } finally {
      setAttBusy(false);
    }
  };
  const removeAttCode = async (code: string) => {
    if (!worker || attBusy) return;
    setAttBusy(true);
    try {
      await mapAttendanceCode(code, null);
      toast(`Đã gỡ ID chấm công ${code}`, "ok");
      loadAttCodes(worker.id);
    } catch (e: any) {
      toast(e?.message || "Lỗi gỡ ID", "err");
    } finally {
      setAttBusy(false);
    }
  };

  // Đổi TÊN — server cascade lịch sử; trang key theo tên nên xong phải đổi hash
  const renameWorker = async () => {
    if (!worker || wkBusy) return;
    const nm = (await promptDialog("Tên mới của nhân viên", { initial: worker.name, okLabel: "Đổi tên" }))?.trim();
    if (!nm || nm === worker.name) return;
    setWkBusy(true);
    try {
      const w = await updateWorker(worker.id, { name: nm });
      toast(`Đã đổi tên → "${w.name}" (lịch sử giữ nguyên)`, "ok");
      location.replace(`#/sx-tho/${encodeURIComponent(w.name)}`);
    } catch (e: any) {
      toast(e?.message || "Lỗi đổi tên", "err");
    } finally {
      setWkBusy(false);
    }
  };

  // Ngày vào làm + ghi chú hồ sơ
  const saveStartDate = async (v: string) => {
    if (!worker) return;
    try {
      const w = await updateWorker(worker.id, { start_date: v });
      setWorker(w);
      toast(v ? `Đã lưu ngày vào làm ${dmy(v)}` : "Đã xoá ngày vào làm", "ok");
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu ngày vào làm", "err");
    }
  };
  const [noteDraft, setNoteDraft] = useState<string | null>(null);
  const saveNote = async () => {
    if (!worker || noteDraft === null) return;
    const v = noteDraft.trim();
    setNoteDraft(null);
    if (v === (worker.note || "")) return;
    try {
      const w = await updateWorker(worker.id, { note: v });
      setWorker(w);
      toast("Đã lưu ghi chú", "ok");
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu ghi chú", "err");
    }
  };

  const load = () => {
    setLoading(true);
    const { from, to } = rangeFor(period);
    getWorkerReport(name, from, to)
      .then((d) => { setData(d); setErr(""); })
      .catch((e: any) => setErr(e?.message || "Lỗi tải dữ liệu"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, [name, period]);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "production_changed" || e.type === "productions_changed" || e.type === "resync") {
        clearTimeout(t); t = setTimeout(load, 500);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, [name, period]);

  // Tiền công CHỈ cho văn phòng (server chỉ đính kèm khi office; client gate thêm)
  const showMoney = isOffice() && !!data?.can_money;
  // Gộp rows theo ngày (giữ thứ tự mới→cũ từ server)
  const days: { ymd: string; date: string; rows: WorkerReportRow[]; tong: number; money: number }[] = [];
  for (const r of data?.rows || []) {
    let g = days.find((x) => x.ymd === r.ymd);
    if (!g) { g = { ymd: r.ymd, date: r.date || dmy(r.ymd), rows: [], tong: 0, money: 0 }; days.push(g); }
    g.rows.push(r);
    g.tong += r.tong_calc;
    g.money += r.money || 0;
  }

  // In phiếu lương (office): sang trang "In phiếu lương" với thợ này chọn sẵn — ở đó
  // chọn khoảng ngày rồi in (chung công cụ với in nhiều thợ).
  const openPayslip = () => {
    location.hash = `#/in-luong?w=${encodeURIComponent(name)}`;
  };

  return (
    <div class="prod-detail">
      <div class="prod-detail-head">
        <BackLink fallback="#/sx-bang" />
        <div>
          <div class="prod-sp">
            <Icon name="user" size={18} /> {name}
            {isOffice() && worker && (
              <button class="icon-btn wd-rename" title="Đổi tên nhân viên" onClick={renameWorker}>
                <Icon name="edit" size={15} />
              </button>
            )}
          </div>
          {data && <div class="muted small">Tổng <b>{soVN(data.total)}</b> SP · {soVN(data.total_mam)} mâm · {data.phieu} phiếu</div>}
          {data && showMoney && <div class="wd-total-money">Tiền công: <b>{money(data.total_money || 0)}</b></div>}
          {data && showMoney && (
            <button class="btn wd-print-btn" onClick={openPayslip} title="Sang trang in phiếu lương — chọn khoảng ngày">
              <Icon name="printer" size={16} /> In phiếu lương
            </button>
          )}
        </div>
      </div>

      {isOffice() && worker && (
        <div class="card wd-weekly-row" onClick={flipWeekly} role="switch" aria-checked={!!worker.weekly_salary}>
          <span class="wd-weekly-label">Nhận lương tuần</span>
          <span class={worker.weekly_salary ? "tgl on" : "tgl"} style={wkBusy ? { opacity: 0.5 } : undefined}>
            <span class="tgl-knob" />
          </span>
        </div>
      )}

      {isOffice() && worker && (
        <div class="card wd-weekly-row">
          <span class="wd-weekly-label">Tiền 1 giờ làm <span class="muted small">(SP tính lương theo giờ)</span></span>
          <span class="wd-rate">
            <input class="pw-input" inputMode="numeric" placeholder="0"
              value={rateDraft !== null ? rateDraft : (worker.hourly_rate ? String(Math.round(worker.hourly_rate)) : "")}
              onInput={(e: any) => setRateDraft(e.target.value)}
              onBlur={saveRate}
              onKeyDown={(e: any) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
            <span class="muted small"> đ/giờ</span>
          </span>
        </div>
      )}

      {isOffice() && worker && (
        <div class="card wd-weekly-row">
          <span class="wd-weekly-label">Ngày vào làm</span>
          <input class="pw-input" type="date" value={worker.start_date || ""}
            onChange={(e: any) => saveStartDate(e.target.value || "")} />
        </div>
      )}

      {isOffice() && worker && (
        <div class="card wd-note-card">
          <span class="wd-weekly-label">Ghi chú</span>
          <textarea class="pw-input wd-note" rows={2} placeholder="ghi chú về nhân viên…"
            value={noteDraft !== null ? noteDraft : (worker.note || "")}
            onInput={(e: any) => setNoteDraft(e.target.value)}
            onBlur={saveNote} />
        </div>
      )}

      {isOffice() && worker && (
        <div class="card wd-weekly-row">
          <span class="wd-weekly-label">ID chấm công <span class="muted small">(mã NV trên máy)</span></span>
          <span class="att-id-codes">
            {attCodes.map((c) => (
              <span class="att-id-chip" key={c}>
                {c}
                <button class="att-id-x" title={`Gỡ mã ${c}`} disabled={attBusy}
                  onClick={() => removeAttCode(c)}>✕</button>
              </span>
            ))}
            <input class="pw-input" inputMode="numeric" placeholder="nhập mã…" style={{ width: 76 }}
              value={attDraft} disabled={attBusy}
              onInput={(e: any) => setAttDraft(e.target.value)}
              onBlur={addAttCode}
              onKeyDown={(e: any) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
          </span>
        </div>
      )}

      <div class="seg">
        {(["all", "month", "week"] as Period[]).map((p) => (
          <button key={p} class={period === p ? "seg-btn active" : "seg-btn"} onClick={() => setPeriod(p)}>
            {p === "all" ? "Toàn bộ" : p === "month" ? "Tháng này" : "7 ngày"}
          </button>
        ))}
      </div>

      {loading && !data ? (
        <Loading />
      ) : err && !data ? (
        <ErrorState msg={err} onRetry={load} />
      ) : !days.length ? (
        <EmptyState icon="📊">Không có dữ liệu kỳ này.</EmptyState>
      ) : (
        days.map((g) => (
          <section class="card" key={g.ymd || g.date}>
            <div class="row space wd-day-head">
              <label class="card-label" style={{ margin: 0 }}><Icon name="calendar" size={16} /> {dmy(g.ymd) !== "?" ? dmy(g.ymd) : g.date}</label>
              <b>{soVN(g.tong)} SP{showMoney ? <span class="wd-day-money"> · {money(g.money)}</span> : null}</b>
            </div>
            {g.rows.map((r, i) => (
              <a key={i} class="wd-row" href={`#/san_xuat/${r.thread_id}`}>
                <span class="wd-prod">{r.product_code}</span>
                <span class="wd-meta muted small">{(r.so_gio || 0) > 0 ? `${soVN(r.so_gio!)} giờ · ` : ""}{soVN(r.so_mam)} mâm{r.note ? ` · ${r.note}` : ""}</span>
                {showMoney && (r.allowance || 0) > 0 && <span class="wd-pc">PC {money(r.allowance || 0)}</span>}
                {showMoney && r.money != null && <b class="wd-money">{money(r.money)}</b>}
                <b class={r.tong_calc > 0 ? "wd-sp" : "wd-sp muted"}>{soVN(r.tong_calc)}</b>
              </a>
            ))}
          </section>
        ))
      )}
    </div>
  );
}
