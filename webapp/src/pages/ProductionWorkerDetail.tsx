// Chi tiết 1 thợ (#/sx-tho/:name) — mỗi NGÀY làm những phiếu nào, SP gì, bao nhiêu SP.
// Gộp theo ngày (report_ymd), mỗi dòng link tới phiếu SX. Lọc kỳ giống dashboard.
// API: getWorkerReport. Realtime production_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { getWorkerReport, isOffice, listWorkers, soVN, updateWorker, type Worker, type WorkerReport, type WorkerReportRow } from "../api";
import { onRealtime } from "../realtime";
import { Loading } from "../ui/states";
import { Icon } from "../ui/Icon";
import { toast } from "../ui/feedback";

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

  const load = () => {
    setLoading(true);
    const { from, to } = rangeFor(period);
    getWorkerReport(name, from, to).then(setData).catch(() => {}).finally(() => setLoading(false));
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

  return (
    <div class="prod-detail">
      <div class="prod-detail-head">
        <BackLink fallback="#/sx-bang" />
        <div>
          <div class="prod-sp"><Icon name="user" size={18} /> {name}</div>
          {data && <div class="muted small">Tổng <b>{soVN(data.total)}</b> SP · {soVN(data.total_mam)} mâm · {data.phieu} phiếu</div>}
          {data && showMoney && <div class="wd-total-money">Tiền công: <b>{money(data.total_money || 0)}</b></div>}
        </div>
      </div>

      {isOffice() && worker && (
        <div class="card wd-weekly-row" onClick={flipWeekly} role="switch" aria-checked={!!worker.weekly_salary}>
          <span class="wd-weekly-label">Nhận lương tuần</span>
          <span class={worker.weekly_salary ? "wd-sw on" : "wd-sw"} style={wkBusy ? { opacity: 0.5 } : undefined}>
            <span class="wd-sw-knob" />
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

      <div class="db-period">
        {(["all", "month", "week"] as Period[]).map((p) => (
          <button key={p} class={period === p ? "db-seg on" : "db-seg"} onClick={() => setPeriod(p)}>
            {p === "all" ? "Toàn bộ" : p === "month" ? "Tháng này" : "7 ngày"}
          </button>
        ))}
      </div>

      {loading && !data ? (
        <Loading />
      ) : !days.length ? (
        <p class="muted small">Không có dữ liệu kỳ này.</p>
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
