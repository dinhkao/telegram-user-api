// Chi tiết LỢI NHUẬN 1 KHÁCH (#/loi-nhuan/khach/:name, office)
// ← GET /api/profit/customer?name=. Tóm tắt + SP hay mua + từng đơn (bung dòng).
import { useEffect, useState } from "preact/hooks";
import { getJSON } from "../api";
import { money, fmtQty } from "../format";
import { ProfitDateBar, presetRange, type DateRange } from "../detail/ProfitDateBar";
import { PageHead } from "../ui/PageHead";
import { Loading, ErrorState, EmptyState } from "../ui/states";

export function ProfitCustomer({ name }: { name: string }) {
  const [range, setRange] = useState<DateRange>(() => presetRange("this_month"));
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const load = () => {
    setErr("");
    getJSON(`/api/profit/customer?name=${encodeURIComponent(name)}&since=${range.since}&until=${range.until}`, { cache: false })
      .then(setData).catch((e: any) => setErr(e?.message || "Lỗi tải"));
  };
  useEffect(load, [name, range.since, range.until]);
  if (err && !data) return <div class="prod-detail"><PageHead fallback="#/loi-nhuan/khach" title={name} /><ErrorState msg={err} onRetry={load} /></div>;
  const t = data?.totals;
  return (
    <div class="prod-detail">
      <PageHead fallback="#/loi-nhuan/khach" title={name} sub={`Lợi nhuận · ${range.since} → ${range.until}`} />
      <ProfitDateBar range={range} onChange={setRange} />
      {!data ? <Loading /> : (
        <>
          <div class="pf-cards">
            <div class="card pf-card"><h4>Doanh thu</h4><b>{money(t.revenue)}</b></div>
            <div class="card pf-card"><h4>Giá vốn</h4><b>{money(t.cost)}</b></div>
            <div class="card pf-card"><h4>Lãi</h4><b class={t.profit >= 0 ? "t-ok" : "t-danger"}>{money(t.profit)}</b></div>
            <div class="card pf-card"><h4>Số đơn</h4><b>{t.orders}</b></div>
          </div>
          <div class="card">
            <div class="ie-head">Sản phẩm đã mua <span class="ie-count">{data.products.length}</span></div>
            {!data.products.length ? <EmptyState>Không có đơn trong khoảng ngày.</EmptyState> : (
              <table class="inv-mini pf-table">
                <thead><tr><th>SP</th><th class="num">SL</th><th class="num">DT</th><th class="num">Lãi</th></tr></thead>
                <tbody>{data.products.map((p: any) => (
                  <tr key={p.code}>
                    <td><a href={`#/loi-nhuan/sp/${encodeURIComponent(p.code)}`}>{p.code}</a></td>
                    <td class="num">{fmtQty(p.qty)}</td>
                    <td class="num">{money(p.revenue)}</td>
                    <td class="num"><b class={p.profit >= 0 ? "t-ok" : "t-danger"}>{money(p.profit)}</b></td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          </div>
          <div class="card">
            <div class="ie-head">Từng đơn <span class="ie-count">{data.orders.length}</span></div>
            <table class="inv-mini pf-table">
              <thead><tr><th>Đơn</th><th class="num">DT</th><th class="num">Lãi</th></tr></thead>
              <tbody>
                {data.orders.map((o: any) => (
                  <>
                    <tr key={o.thread_id} onClick={() => setOpen(open === o.thread_id ? null : o.thread_id)}>
                      <td><a href={`#/order/${o.thread_id}`} onClick={(e) => e.stopPropagation()}>#{o.thread_id}</a>
                        {" "}<span class="muted small">{o.date}</span></td>
                      <td class="num">{money(o.revenue)}</td>
                      <td class="num"><b class={o.profit >= 0 ? "t-ok" : "t-danger"}>{money(o.profit)}</b></td>
                    </tr>
                    {open === o.thread_id && (
                      <tr class="pf-expand"><td colSpan={3}>
                        <table class="inv-mini"><tbody>
                          {o.items.map((it: any, i: number) => (
                            <tr key={i}><td>{it.code}</td><td class="num">{fmtQty(it.qty)}</td>
                              <td class="num">{money(it.sell_price)}</td>
                              <td class="num">{it.has_cost ? money(it.profit) : <span class="t-warn">chưa có vốn</span>}</td></tr>
                          ))}
                        </tbody></table>
                      </td></tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
