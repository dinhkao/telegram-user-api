// Dashboard báo cáo sản xuất (#/sx-bang) — tổng hợp sản lượng theo THỢ / NGÀY / SP từ
// bảng quan hệ production_report_rows. Lọc kỳ: toàn bộ / tháng này / 7 ngày. Thanh bar
// tỉ lệ (không dùng lib). API: getProductionDashboard. Realtime production_changed → tải lại.
import { useEffect, useMemo, useState } from "preact/hooks";
import { getProductionDashboard, soVN, type ProdDashboard } from "../api";
import { onRealtime } from "../realtime";
import { Loading, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";

const pad = (n: number) => String(n).padStart(2, "0");
const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const dmy = (ymd: string) => { const [y, m, d] = ymd.split("-"); return `${d}/${m}`; };

type Period = "all" | "month" | "week";
function rangeFor(p: Period): { from?: string; to?: string } {
  if (p === "all") return {};
  const now = new Date();
  const to = iso(now);
  if (p === "month") return { from: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-01`, to };
  const wk = new Date(now); wk.setDate(now.getDate() - 6);
  return { from: iso(wk), to };
}

function Bar({ label, sub, val, max, href }: { label: string; sub?: string; val: number; max: number; href?: string }) {
  const pct = max > 0 ? Math.max(2, Math.round((val / max) * 100)) : 0;
  const inner = (
    <>
      <div class="db-row-head"><span class="db-name">{label}</span><b class="db-val">{soVN(val)}</b></div>
      <div class="db-bar"><div class="db-bar-fill" style={{ width: pct + "%" }} /></div>
      {sub && <span class="db-sub muted small">{sub}</span>}
    </>
  );
  return href ? <a class="db-row db-link" href={href}>{inner}</a> : <div class="db-row">{inner}</div>;
}

// Nhớ kỳ đã chọn khi rời trang (module scope)
let memPeriod: Period = "month";

export function ProductionDashboard() {
  const [period, setPeriod] = useState<Period>(memPeriod);
  useEffect(() => { memPeriod = period; }, [period]);
  const [data, setData] = useState<ProdDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const load = () => {
    setLoading(true);
    const { from, to } = rangeFor(period);
    getProductionDashboard(from, to)
      .then((d) => { setData(d); setErr(""); })
      .catch((e: any) => setErr(e?.message || "Lỗi tải dữ liệu"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, [period]);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "production_changed" || e.type === "productions_changed" || e.type === "resync") {
        clearTimeout(t); t = setTimeout(load, 500);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, [period]);

  const maxW = useMemo(() => (data ? Math.max(1, ...data.by_worker.map((w) => w.tong)) : 1), [data]);
  const maxD = useMemo(() => (data ? Math.max(1, ...data.by_day.map((x) => x.tong)) : 1), [data]);
  const maxP = useMemo(() => (data ? Math.max(1, ...data.by_product.map((p) => p.tong)) : 1), [data]);

  return (
    <div class="db-page">
      <PageHead fallback="#/san_xuat" title={<><Icon name="chart" size={18} /> Dashboard sản xuất</>} />
      <div class="seg">
        {(["all", "month", "week"] as Period[]).map((p) => (
          <button key={p} class={period === p ? "seg-btn active" : "seg-btn"} onClick={() => setPeriod(p)}>
            {p === "all" ? "Toàn bộ" : p === "month" ? "Tháng này" : "7 ngày"}
          </button>
        ))}
      </div>

      {loading && !data ? (
        <Loading />
      ) : data ? (
        <>
          <div class="db-cards">
            <div class="db-card"><span class="db-card-num">{soVN(data.totals.tong)}</span><span class="db-card-lbl">Tổng SP</span></div>
            <div class="db-card"><span class="db-card-num">{data.totals.phieu}</span><span class="db-card-lbl">Phiếu</span></div>
            <div class="db-card"><span class="db-card-num">{data.totals.tho}</span><span class="db-card-lbl">Thợ</span></div>
          </div>

          <section class="card">
            <label class="card-label">🏆 Theo thợ ({data.by_worker.length})</label>
            {data.by_worker.length ? data.by_worker.map((w) => (
              <Bar key={w.name} label={w.name} sub={`${soVN(w.mam)} mâm · ${w.phieu} phiếu`} val={w.tong} max={maxW} href={`#/sx-tho/${encodeURIComponent(w.name)}`} />
            )) : <p class="muted small">Chưa có dữ liệu kỳ này.</p>}
          </section>

          <section class="card">
            <label class="card-label"><Icon name="calendar" size={16} /> Theo ngày</label>
            {data.by_day.length ? data.by_day.map((x) => (
              <Bar key={x.ymd} label={dmy(x.ymd)} sub={`${x.phieu} phiếu`} val={x.tong} max={maxD} />
            )) : <p class="muted small">Chưa có dữ liệu kỳ này.</p>}
          </section>

          <section class="card">
            <label class="card-label"><Icon name="box" size={16} /> Theo sản phẩm</label>
            {data.by_product.length ? data.by_product.map((p) => (
              <Bar key={p.code} label={p.code} sub={`${p.phieu} phiếu`} val={p.tong} max={maxP} />
            )) : <p class="muted small">Chưa có dữ liệu kỳ này.</p>}
          </section>
        </>
      ) : (
        <ErrorState msg={err || "Lỗi tải dữ liệu."} onRetry={load} />
      )}
    </div>
  );
}
