// Lợi nhuận theo KHÁCH HÀNG (#/loi-nhuan/khach, office) ← GET /api/profit/customers.
// Bảng mọi khách trong khoảng ngày, sắp theo lãi; bấm tên → chi tiết khách.
import { useEffect, useState } from "preact/hooks";
import { getJSON } from "../api";
import { money } from "../format";
import { ProfitDateBar, presetRange, type DateRange } from "../detail/ProfitDateBar";
import { PageHead } from "../ui/PageHead";
import { Loading, ErrorState, EmptyState } from "../ui/states";

export function ProfitCustomers() {
  const [range, setRange] = useState<DateRange>(() => presetRange("today"));
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  const load = () => {
    setErr("");
    getJSON(`/api/profit/customers?since=${range.since}&until=${range.until}`, { cache: false })
      .then(setData).catch((e: any) => setErr(e?.message || "Lỗi tải"));
  };
  useEffect(load, [range.since, range.until]);
  if (err && !data) return <div class="prod-detail"><PageHead fallback="#/loi-nhuan" title="Lãi theo khách" /><ErrorState msg={err} onRetry={load} /></div>;
  const t = data?.totals;
  return (
    <div class="prod-detail">
      <PageHead fallback="#/loi-nhuan" title="Lãi theo khách" sub={`${range.since} → ${range.until}`} />
      <ProfitDateBar range={range} onChange={setRange} />
      {!data ? <Loading /> : (
        <div class="card">
          <div class="ie-head">Khách hàng <span class="ie-count">{data.customers.length}</span></div>
          {!data.customers.length ? <EmptyState>Không có đơn trong khoảng ngày này.</EmptyState> : (
            <table class="inv-mini pf-table">
              <thead><tr><th>Khách</th><th class="num">Đơn</th><th class="num">DT</th><th class="num">Lãi</th></tr></thead>
              <tbody>
                {data.customers.map((c: any) => (
                  <tr key={c.name}>
                    <td><a href={`#/loi-nhuan/khach/${encodeURIComponent(c.name)}`}>{c.name}</a>
                      <span class="muted small"> · {c.product_count} SP</span></td>
                    <td class="num">{c.orders}</td>
                    <td class="num">{money(c.revenue)}</td>
                    <td class="num"><b class={c.profit >= 0 ? "t-ok" : "t-danger"}>{money(c.profit)}</b></td>
                  </tr>
                ))}
                <tr class="tot"><td class="lbl">Tổng ({t.orders} đơn)</td><td></td>
                  <td class="num">{money(t.revenue)}</td>
                  <td class="num"><b class={t.profit >= 0 ? "t-ok" : "t-danger"}>{money(t.profit)}</b></td></tr>
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
