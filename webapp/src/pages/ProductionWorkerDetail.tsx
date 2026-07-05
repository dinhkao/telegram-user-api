// Chi tiết 1 thợ (#/sx-tho/:name) — mỗi NGÀY làm những phiếu nào, SP gì, bao nhiêu SP.
// Gộp theo ngày (report_ymd), mỗi dòng link tới phiếu SX. Lọc kỳ giống dashboard.
// API: getWorkerReport. Realtime production_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { getWorkerReport, soVN, type WorkerReport, type WorkerReportRow } from "../api";
import { onRealtime } from "../realtime";
import { Loading } from "../ui/states";

const pad = (n: number) => String(n).padStart(2, "0");
const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const dmy = (ymd: string) => { if (!ymd) return "?"; const [y, m, d] = ymd.split("-"); return `${d}/${m}/${y}`; };

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

  // Gộp rows theo ngày (giữ thứ tự mới→cũ từ server)
  const days: { ymd: string; date: string; rows: WorkerReportRow[]; tong: number }[] = [];
  for (const r of data?.rows || []) {
    let g = days.find((x) => x.ymd === r.ymd);
    if (!g) { g = { ymd: r.ymd, date: r.date || dmy(r.ymd), rows: [], tong: 0 }; days.push(g); }
    g.rows.push(r);
    g.tong += r.tong_calc;
  }

  return (
    <div class="prod-detail">
      <div class="prod-detail-head">
        <BackLink fallback="#/sx-bang" />
        <div>
          <div class="prod-sp">👤 {name}</div>
          {data && <div class="muted small">Tổng <b>{soVN(data.total)}</b> SP · {soVN(data.total_mam)} mâm · {data.phieu} phiếu</div>}
        </div>
      </div>

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
              <label class="card-label" style={{ margin: 0 }}>📅 {dmy(g.ymd) !== "?" ? dmy(g.ymd) : g.date}</label>
              <b>{soVN(g.tong)} SP</b>
            </div>
            {g.rows.map((r, i) => (
              <a key={i} class="wd-row" href={`#/san_xuat/${r.thread_id}`}>
                <span class="wd-prod">{r.product_code}</span>
                <span class="wd-meta muted small">{soVN(r.so_mam)} mâm{r.note ? ` · ${r.note}` : ""}</span>
                <b class={r.tong_calc > 0 ? "wd-sp" : "wd-sp muted"}>{soVN(r.tong_calc)}</b>
              </a>
            ))}
          </section>
        ))
      )}
    </div>
  );
}
