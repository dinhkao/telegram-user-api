// Khối "Báo cáo bán ra" ở trang chi tiết SP (#/kho/:code, CHỈ VĂN PHÒNG) ←
// GET /api/profit/product/{code} (totals + prev/changes kỳ trước + top_customers +
// chart theo ngày). Lazy-load bằng IntersectionObserver (endpoint quét full bảng
// orders — chỉ gọi khi khối lộ ra màn hình); đổi khoảng ngày qua ProfitDateBar
// (dùng chung trang lợi nhuận). Biểu đồ = ProductSalesChart.
import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON, isOffice } from "../api";
import { money, fmtQty } from "../format";
import { ProfitDateBar, presetRange, Chg, type DateRange } from "./ProfitDateBar";
import { ProductSalesChart } from "./ProductSalesChart";
import { Icon } from "../ui/Icon";
import { EmptyState, ErrorState, LoadingInline } from "../ui/states";

const dmy = (ymd: string) => ymd ? `${ymd.slice(8, 10)}/${ymd.slice(5, 7)}` : "";
const RECENT_N = 6;

// Cache theo MÃ (module scope): back về trang chi tiết SP là khối render ngay với
// đúng khoảng ngày đã chọn → useScrollMemory khôi phục vị trí không hụt chiều cao.
const _cache = new Map<string, { range: DateRange; data: any }>();

function Stat({ label, value, chg, sub }: { label: string; value: any; chg?: number | null; sub?: string }) {
  return (
    <div class="card pf-card">
      <h4>{label}</h4>
      <b>{value}</b>
      {chg !== undefined && <Chg v={chg} nullLabel="kỳ trước 0" />}
      {sub && <div class="muted" style="font-size:.68rem">{sub}</div>}
    </div>
  );
}

function TopCustomers({ tops, totalRev }: { tops: any[]; totalRev: number }) {
  const [all, setAll] = useState(false);
  const rows = all ? tops : tops.slice(0, 10);
  const maxRev = rows.length ? Math.max(...rows.map((c) => c.revenue), 1) : 1;
  return (
    <>
      <div class="ie-head" style={{ marginTop: "8px" }}>
        Top khách hàng <span class="ie-count">{tops.length}</span>
      </div>
      <table class="inv-mini pf-table">
        <thead><tr><th>Khách</th><th class="num">SL</th><th class="num">Giá TB</th><th class="num">Doanh thu</th></tr></thead>
        <tbody>{rows.map((c) => (
          <tr key={c.name}>
            <td>
              <a href={`#/loi-nhuan/khach/${encodeURIComponent(c.name)}`}>{c.name}</a>
              <div class="muted" style="font-size:.7rem">
                {c.orders} đơn · gần nhất {dmy(c.last_ymd)}{totalRev > 0 && ` · ${Math.round((c.revenue / totalRev) * 100)}%`}
              </div>
              <div style={{ height: "3px", borderRadius: "2px", background: "#3b82f6", opacity: 0.55, width: `${Math.max(3, Math.round((c.revenue / maxRev) * 100))}%` }} />
            </td>
            <td class="num">{fmtQty(c.qty)}</td>
            <td class="num">{money(c.avg_price)}</td>
            <td class="num">{money(c.revenue)}</td>
          </tr>
        ))}</tbody>
      </table>
      {tops.length > 10 && (
        <button class="btn small" style="margin-top:6px" onClick={() => setAll(!all)}>
          {all ? "Thu gọn" : `Xem cả ${tops.length} khách`}
        </button>
      )}
    </>
  );
}

function RecentSales({ orders, code }: { orders: any[]; code: string }) {
  const recent = [...orders]
    .sort((a, b) => (b.ymd || "").localeCompare(a.ymd || "") || b.thread_id - a.thread_id)
    .slice(0, RECENT_N);
  return (
    <>
      <div class="ie-head" style={{ marginTop: "8px" }}>
        Lần bán gần đây <span class="ie-count">{orders.length}</span>
      </div>
      <table class="inv-mini pf-table">
        <tbody>{recent.map((o) => (
          <tr key={`${o.thread_id}-${o.sell_price}`}>
            <td class="muted small" style="white-space:nowrap">{dmy(o.ymd)}</td>
            <td><a href={`#/loi-nhuan/khach/${encodeURIComponent(o.customer)}`}>{o.customer}</a></td>
            <td class="num" style="white-space:nowrap">{fmtQty(o.qty)} × {money(o.sell_price)}</td>
            <td class="num"><a href={`#/order/${o.thread_id}`}>#{o.thread_id}</a></td>
          </tr>
        ))}</tbody>
      </table>
      {orders.length > RECENT_N && (
        <a class="btn small" style="margin-top:6px" href={`#/loi-nhuan/sp/${encodeURIComponent(code)}`}>
          Xem cả {orders.length} lần bán →
        </a>
      )}
    </>
  );
}

export function ProductSales({ code }: { code: string }) {
  const cached = _cache.get(code);
  const [range, setRange] = useState<DateRange>(() => cached?.range || presetRange("this_month"));
  const [data, setData] = useState<any>(cached?.data || null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const started = useRef(!!cached);
  const secRef = useRef<HTMLElement>(null);

  const load = () => {
    setErr("");
    setLoading(true);
    getJSON(`/api/profit/product/${encodeURIComponent(code)}?since=${range.since}&until=${range.until}`, { cache: false })
      .then((j) => { setData(j); _cache.set(code, { range, data: j }); })
      .catch((e: any) => setErr(e?.message || "Lỗi tải báo cáo bán ra"))
      .finally(() => setLoading(false));
  };
  // Đổi mã SP → về trạng thái cache của mã đó (hoặc chưa tải, chờ khối lộ ra)
  useEffect(() => {
    const c = _cache.get(code);
    started.current = !!c;
    setData(c?.data || null);
    if (c) setRange(c.range);
  }, [code]);
  useEffect(() => {
    const el = secRef.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting && !started.current) { started.current = true; load(); }
    }, { rootMargin: "200px" });
    io.observe(el);
    return () => io.disconnect();
  }, [code]);
  useEffect(() => { if (started.current) load(); }, [range.since, range.until]);

  if (!isOffice()) return null;
  const t = data?.totals;
  const ch = data?.changes || {};
  const prev = data?.prev;
  return (
    <section class="card" ref={secRef}>
      <div class="row space">
        <label class="card-label" style={{ margin: 0 }}>Báo cáo bán ra</label>
        <a class="btn small" href={`#/loi-nhuan/sp/${encodeURIComponent(code)}`}>
          <Icon name="chart" size={14} /> Lợi nhuận →
        </a>
      </div>
      {!started.current || (loading && !data) ? (
        <div class="muted small"><LoadingInline /></div>
      ) : err && !data ? (
        <ErrorState msg={err} onRetry={load} />
      ) : !data ? null : (
        <div style={loading ? "opacity:.6" : ""}>
          <ProfitDateBar range={range} onChange={setRange} />
          <div class="pf-cards">
            <Stat label="SL bán" value={fmtQty(t.qty)} chg={ch.qty} />
            <Stat label="Doanh thu" value={money(t.revenue)} chg={ch.revenue} />
            <Stat label="Giá bán TB" value={money(t.avg_price || 0)} chg={ch.avg_price} />
            <Stat label="Số đơn" value={t.orders ?? data.orders.length} chg={ch.orders} />
            <Stat label="Số khách" value={t.customers || 0} chg={ch.customers} />
            {prev && (
              <Stat label={`Kỳ trước ${dmy(prev.since)}–${dmy(prev.until)}`} value={money(prev.revenue)}
                sub={`${fmtQty(prev.qty)} · ${prev.orders} đơn · ${prev.customers} khách`} />
            )}
          </div>
          {!data.orders.length ? (
            <EmptyState>Không có lần bán nào trong khoảng ngày.</EmptyState>
          ) : (
            <>
              <ProductSalesChart chart={data.chart || []} since={range.since} until={range.until} />
              <TopCustomers tops={data.top_customers || []} totalRev={t.revenue} />
              <RecentSales orders={data.orders} code={code} />
            </>
          )}
        </div>
      )}
    </section>
  );
}
