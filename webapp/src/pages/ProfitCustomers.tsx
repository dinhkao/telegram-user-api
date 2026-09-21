// Lợi nhuận theo KHÁCH HÀNG (#/loi-nhuan/khach, office) ← GET /api/profit/customers.
// Như bản gốc: 4 thẻ tóm tắt (tổng khách/DT/vốn/lãi) + bảng mọi khách (đơn, SP,
// DT, vốn, lãi, biên LN) sắp theo lãi; bấm tên → chi tiết khách.
import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON } from "../api";
import { money } from "../format";
import { initialProfitRange } from "../detail/profitDates";
import { ProfitDateBar, type DateRange } from "../detail/ProfitDateBar";
import { ProfitQualityNote, ProfitCoverageNote } from "../detail/ProfitOverview";
import { PageHead } from "../ui/PageHead";
import { Loading, ErrorState, EmptyState } from "../ui/states";

export function ProfitCustomers() {
  const [range, setRange] = useState<DateRange>(() => initialProfitRange("today"));
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  const requestId = useRef(0);
  const load = () => {
    const id = ++requestId.current;
    setData(null); setErr("");
    getJSON(`/api/profit/customers?since=${range.since}&until=${range.until}`, { cache: false })
      .then(j => { if (id === requestId.current) setData(j); }).catch((e: any) => { if (id === requestId.current) setErr(e?.message || "Lỗi tải"); });
  };
  useEffect(() => { load(); return () => { requestId.current++; }; }, [range.since, range.until]);
  if (err && !data) return <div class="prod-detail"><PageHead fallback="#/loi-nhuan" title="Lãi theo khách" /><ErrorState msg={err} onRetry={load} /></div>;
  const t = data?.totals;
  return (
    <div class="prod-detail">
      <PageHead fallback="#/loi-nhuan" title="Lãi theo khách" sub={`${range.since} → ${range.until}`} />
      <ProfitDateBar range={range} onChange={setRange} />
      {!data ? <Loading /> : (
        <>
          <ProfitQualityNote t={t} /><ProfitCoverageNote coverage={data.coverage} />
          <p class="muted small">Doanh thu chưa VAT, đã giảm hàng trả xác nhận. Lãi đơn đã cộng VAT thu khách vì giá vốn đã dự tính VAT bán ra. Chưa trừ lãi vay và các chi phí vận hành khác.</p>
          <div class="pf-cards">
            <div class="card pf-card"><h4>Tổng khách</h4><b>{data.customers.length}</b></div>
            <div class="card pf-card"><h4>Doanh thu</h4><b>{money(t.revenue)}</b></div>
            <div class="card pf-card"><h4>Giá vốn</h4><b>{money(t.cost)}</b></div>
            <div class="card pf-card"><h4>{t.cost_complete ? "Lãi gộp" : "Lãi đã xác định"}</h4><b class={t.profit >= 0 ? "t-ok" : "t-danger"}>{money(t.profit)}</b></div>
          </div>
          <div class="card">
            <div class="ie-head">Khách hàng <span class="ie-count">{data.customers.length}</span></div>
            {!data.customers.length ? <EmptyState>Không có đơn trong khoảng ngày này.</EmptyState> : (
              <table class="inv-mini pf-table">
                <thead><tr><th>Khách</th><th class="num">Đơn</th><th class="num">DT</th><th class="num">Vốn</th><th class="num">Lãi · biên</th></tr></thead>
                <tbody>
                  {data.customers.map((c: any) => {
                    const margin = !c.missing_cost_orders && c.revenue > 0 ? ((c.profit / c.revenue) * 100).toFixed(1) : "—";
                    return (
                      <tr key={c.name}>
                        <td><a href={`#/loi-nhuan/khach/${encodeURIComponent(c.name)}?${new URLSearchParams(range)}`}>{c.name}</a>
                          <span class="muted small"> · {c.product_count} SP</span></td>
                        <td class="num">{c.orders}</td>
                        <td class="num">{money(c.revenue)}</td>
                        <td class="num">{money(c.cost)}</td>
                        <td class="num"><><b class={c.profit >= 0 ? "t-ok" : "t-danger"}>{money(c.profit)}{c.missing_cost_orders ? " *" : ""}</b>
                              <div class="muted small">{margin}{margin === "—" ? "" : "%"}</div></></td>
                      </tr>
                    );
                  })}
                  <tr class="tot"><td class="lbl">Tổng ({t.orders} đơn)</td><td></td>
                    <td class="num">{money(t.revenue)}</td>
                    <td class="num">{money(t.cost)}</td>
                    <td class="num"><b class={t.profit >= 0 ? "t-ok" : "t-danger"}>{money(t.profit)}</b></td></tr>
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}
