// Dashboard LỢI NHUẬN native (#/loi-nhuan, CHỈ văn phòng) — thay bộ trang HTML
// /loi-nhuan/* cũ (gỡ 2026-08-26). Nguồn: GET /api/profit/dashboard. Gồm: chọn
// khoảng ngày, thẻ tóm tắt (so % kỳ trước, LÃI THỰC = lãi gộp − tiền vay phân
// bổ), top 5 khách/SP, 3 tab: Đơn hàng (feed) · Sản phẩm (sửa giá vốn hàng
// loạt) · Biểu đồ (SVG lãi theo ngày). Trang con: #/loi-nhuan/khach, /sp/:code,
// /cai-dat.
import { useEffect, useState } from "preact/hooks";
import { getJSON, postJSON, isOffice } from "../api";
import { money, fmtQty } from "../format";
import { ProfitDateBar, Chg, presetRange, type DateRange } from "../detail/ProfitDateBar";
import { ProfitOrdersFeed } from "../detail/ProfitOrdersFeed";
import { toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { Loading, ErrorState, EmptyState } from "../ui/states";

function SummaryCards({ s }: { s: any }) {
  return (
    <>
      <div class="pf-cards">
        <div class="card pf-card"><h4>Doanh thu</h4><b>{money(s.revenue)}</b><Chg v={s.changes?.revenue} /></div>
        <div class="card pf-card"><h4>Giá vốn</h4><b>{money(s.cost)}</b><Chg v={s.changes?.cost} /></div>
        <div class="card pf-card"><h4>Lãi gộp</h4><b class={s.profit >= 0 ? "t-ok" : "t-danger"}>{money(s.profit)}</b><Chg v={s.changes?.profit} /></div>
        <div class="card pf-card"><h4>Số đơn</h4><b>{s.orders}</b><Chg v={s.changes?.orders} /></div>
      </div>
      <div class="card pf-real">
        <h4>LÃI THỰC (sau tiền vay)</h4>
        <b>{money(s.real_profit)}</b>
        <div class="small">vay phân bổ kỳ này: {money(s.loan)} · biên {s.margin}%</div>
        {s.prev_label ? <div class="small" style="opacity:.8">so kỳ trước {s.prev_label}: lãi {money(s.prev?.profit || 0)}</div> : null}
      </div>
    </>
  );
}

function TopLists({ d }: { d: any }) {
  return (
    <div class="pf-tops">
      <div class="card">
        <div class="ie-head">Top khách (lãi)</div>
        {(d.top_customers || []).map((c: any, i: number) => (
          <a key={c.name} class="pf-top-row" href={`#/loi-nhuan/khach/${encodeURIComponent(c.name)}`}>
            <span class="pf-rank">{i + 1}</span>
            <span class="pf-top-name">{c.name}</span>
            <span class="num"><b class={c.profit >= 0 ? "t-ok" : "t-danger"}>{money(c.profit)}</b>
              <span class="muted small"> · {c.orders} đơn</span></span>
          </a>
        ))}
      </div>
      <div class="card">
        <div class="ie-head">Top sản phẩm (lãi)</div>
        {(d.top_products || []).map((p: any, i: number) => (
          <a key={p.code} class="pf-top-row" href={`#/loi-nhuan/sp/${encodeURIComponent(p.code)}`}>
            <span class="pf-rank">{i + 1}</span>
            <span class="pf-top-name">{p.code}</span>
            <span class="num"><b class={p.profit >= 0 ? "t-ok" : "t-danger"}>{money(p.profit)}</b>
              <span class="muted small"> · {fmtQty(p.qty)}</span></span>
          </a>
        ))}
      </div>
    </div>
  );
}

// Tab Sản phẩm: bảng lãi theo SP + Ô GIÁ VỐN MỚI sửa hàng loạt → POST /api/profit/costs
function ProductCostTable({ products, onSaved }: { products: any[]; onSaved: () => void }) {
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const dirty = Object.entries(edits).filter(([, v]) => v.trim() !== "");
  const save = async () => {
    const updates: Record<string, number> = {};
    for (const [code, v] of dirty) {
      const n = parseInt(v.replace(/[.,\s]/g, ""), 10);
      if (!isNaN(n) && n >= 0) updates[code] = n;
    }
    if (!Object.keys(updates).length) { toast("Chưa nhập giá vốn mới nào", "info"); return; }
    setBusy(true);
    try {
      await postJSON("/api/profit/costs", { updates });
      toast(`Đã lưu giá vốn ${Object.keys(updates).length} SP`, "ok");
      setEdits({});
      onSaved();
    } catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); }
    finally { setBusy(false); }
  };
  return (
    <div class="card">
      <div class="row space">
        <div class="ie-head">Lợi nhuận theo SP <span class="ie-count">{products.length} mã</span></div>
        <button class="btn small primary" disabled={busy || !dirty.length} onClick={save}>
          <Icon name="save" size={14} /> Lưu giá vốn{dirty.length ? ` (${dirty.length})` : ""}
        </button>
      </div>
      <table class="inv-mini pf-table">
        <thead><tr><th>SP</th><th class="num">Vốn</th><th class="num">Vốn mới</th><th class="num">SL</th><th class="num">Lãi</th></tr></thead>
        <tbody>
          {products.map((p) => (
            <tr key={p.code}>
              <td><a href={`#/loi-nhuan/sp/${encodeURIComponent(p.code)}`} title={p.name}>{p.code}</a></td>
              <td class="num">{p.cost_price ? money(p.cost_price) : <span class="t-warn">chưa có</span>}</td>
              <td class="num"><input class="pf-cost-inp" inputMode="numeric" placeholder="giá"
                value={edits[p.code] ?? ""}
                onInput={(e: any) => setEdits((prev) => ({ ...prev, [p.code]: e.target.value }))} /></td>
              <td class="num">{fmtQty(p.qty)}</td>
              <td class="num"><b class={p.profit >= 0 ? "t-ok" : "t-danger"}>{money(p.profit)}</b></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Tab Biểu đồ: cột LÃI THỰC theo ngày (SVG thuần, không thư viện)
function ProfitChart({ chart }: { chart: any[] }) {
  if (!chart.length) return <EmptyState>Chưa có dữ liệu trong khoảng ngày này.</EmptyState>;
  const W = 900, H = 240, PAD = 4;
  const vals = chart.map((c) => c.real_profit);
  const max = Math.max(...vals, 1), min = Math.min(...vals, 0);
  const span = max - min || 1;
  const bw = (W - PAD * 2) / chart.length;
  const y0 = PAD + (max / span) * (H - PAD * 2);   // đường 0
  return (
    <div class="card" style="overflow-x:auto">
      <div class="ie-head">Lãi thực theo ngày <span class="ie-count">{chart.length} ngày</span></div>
      <svg viewBox={`0 0 ${W} ${H + 18}`} style="width:100%;min-width:480px">
        <line x1={PAD} x2={W - PAD} y1={y0} y2={y0} stroke="var(--muted)" stroke-width="0.5" />
        {chart.map((c, i) => {
          const h = (Math.abs(c.real_profit) / span) * (H - PAD * 2);
          const y = c.real_profit >= 0 ? y0 - h : y0;
          return (
            <g key={c.day}>
              <rect x={PAD + i * bw + 1} y={y} width={Math.max(1, bw - 2)} height={Math.max(1, h)}
                fill={c.real_profit >= 0 ? "#22c55e" : "#ef4444"}>
                <title>{c.day}: lãi thực {money(c.real_profit)} (DT {money(c.revenue)})</title>
              </rect>
              {chart.length <= 31 && i % Math.ceil(chart.length / 10) === 0 && (
                <text x={PAD + i * bw + bw / 2} y={H + 12} font-size="9" text-anchor="middle"
                  fill="currentColor" opacity="0.6">{c.day.slice(8, 10)}/{c.day.slice(5, 7)}</text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function ProfitDashboard() {
  const [range, setRange] = useState<DateRange>(() => presetRange("today"));
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState<string>(() => sessionStorage.getItem("pf_tab") || "don");
  const pickTab = (t: string) => { setTab(t); sessionStorage.setItem("pf_tab", t); };

  const load = () => {
    setErr("");
    getJSON(`/api/profit/dashboard?since=${range.since}&until=${range.until}`, { cache: false })
      .then(setData).catch((e: any) => setErr(e?.message || "Lỗi tải"));
  };
  useEffect(load, [range.since, range.until]);

  if (!isOffice()) return <div class="prod-detail"><PageHead fallback="#/home" title="Lợi nhuận" /><EmptyState>Chỉ văn phòng được xem trang lợi nhuận.</EmptyState></div>;
  if (err && !data) return <div class="prod-detail"><PageHead fallback="#/home" title="Lợi nhuận" /><ErrorState msg={err} onRetry={load} /></div>;

  return (
    <div class="prod-detail">
      <PageHead fallback="#/home" title="Lợi nhuận" sub={`${range.since} → ${range.until}`}
        right={<span class="row">
          <a class="btn small" href="#/loi-nhuan/khach"><Icon name="users" size={14} /> Khách</a>
          <a class="btn small" href="#/loi-nhuan/cai-dat"><Icon name="settings" size={14} /></a>
        </span>} />
      <ProfitDateBar range={range} onChange={setRange} />
      {!data ? <Loading /> : (
        <>
          <SummaryCards s={data.summary} />
          <TopLists d={data} />
          <div class="seg mt-2">
            {[["don", "Đơn hàng"], ["sp", "Sản phẩm"], ["chart", "Biểu đồ"]].map(([k, label]) => (
              <button key={k} class={"seg-btn" + (tab === k ? " active" : "")} onClick={() => pickTab(k)}>{label}</button>
            ))}
          </div>
          {tab === "don" && <ProfitOrdersFeed range={range} />}
          {tab === "sp" && <ProductCostTable products={data.products || []} onSaved={load} />}
          {tab === "chart" && <ProfitChart chart={data.chart || []} />}
        </>
      )}
    </div>
  );
}
