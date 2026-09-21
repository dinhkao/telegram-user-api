// Chi tiết LỢI NHUẬN 1 KHÁCH (#/loi-nhuan/khach/:name, office)
// ← GET /api/profit/customer?name=. Như bản gốc: tóm tắt + Ô LỌC THEO MÃ SP
// (tóm tắt tính lại theo lọc) + SP hay mua + lịch sử đơn (chip SP, cột giá vốn,
// bung dòng xem chi tiết từng SP).
import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON } from "../api";
import { money, fmtQty } from "../format";
import { initialProfitRange } from "../detail/profitDates";
import { ProfitDateBar, type DateRange } from "../detail/ProfitDateBar";
import { ProfitQualityNote, ProfitCoverageNote } from "../detail/ProfitOverview";
import { PageHead } from "../ui/PageHead";
import { Loading, ErrorState, EmptyState } from "../ui/states";

export function ProfitCustomer({ name }: { name: string }) {
  const [range, setRange] = useState<DateRange>(() => initialProfitRange("this_month"));
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [fp, setFp] = useState("");   // lọc theo mã SP (client-side, như bản gốc)
  const requestId = useRef(0);
  const load = () => {
    const id = ++requestId.current;
    setData(null); setErr("");
    getJSON(`/api/profit/customer?name=${encodeURIComponent(name)}&since=${range.since}&until=${range.until}`, { cache: false })
      .then(j => { if (id === requestId.current) setData(j); }).catch((e: any) => { if (id === requestId.current) setErr(e?.message || "Lỗi tải"); });
  };
  useEffect(() => { load(); return () => { requestId.current++; }; }, [name, range.since, range.until]);
  if (err && !data) return <div class="prod-detail"><PageHead fallback="#/loi-nhuan/khach" title={name} /><ErrorState msg={err} onRetry={load} /></div>;

  const fpc = fp.trim().toUpperCase();
  const orders = (data?.orders || []).filter((o: any) =>
    !fpc || (o.items || []).some((it: any) => String(it.code).includes(fpc)));
  // Tóm tắt tính lại theo lọc (bản gốc cũng vậy khi ?product=)
  const t = fpc
    ? {
        revenue: orders.reduce((s: number, o: any) => s + o.revenue, 0),
        cost: orders.reduce((s: number, o: any) => s + o.cost, 0),
        profit: orders.reduce((s: number, o: any) => s + o.profit, 0),
        orders: orders.filter((o: any) => o.kind === "sale").length,
        returns: orders.filter((o: any) => o.kind === "return").length,
        cost_complete: orders.every((o: any) => o.cost_complete),
        missing_cost_lines: orders.reduce((s: number, o: any) => s + o.items.filter((i: any) => !i.has_cost).length, 0),
      }
    : data?.totals;
  return (
    <div class="prod-detail">
      <PageHead fallback="#/loi-nhuan/khach" title={name} sub={`Lợi nhuận · ${range.since} → ${range.until}`} />
      <ProfitDateBar range={range} onChange={setRange} />
      {!data ? <Loading /> : (
        <>
          <div class="card pf-filterbar">
            <input class="note-inp" placeholder="Lọc theo mã SP" value={fp}
              onInput={(e: any) => setFp(e.target.value)} />
            {fp && <button class="btn small" onClick={() => setFp("")}>Xoá lọc</button>}
          </div>
          <ProfitQualityNote t={t} /><ProfitCoverageNote coverage={data.coverage} />
          <p class="muted small">Doanh thu chưa VAT, đã giảm hàng trả xác nhận. Lãi đơn đã cộng VAT thu khách vì giá vốn đã dự tính VAT bán ra. Chưa trừ lãi vay và các chi phí vận hành khác.</p>
          <div class="pf-cards">
            <div class="card pf-card"><h4>Doanh thu</h4><b>{money(t.revenue)}</b></div>
            <div class="card pf-card"><h4>Giá vốn</h4><b>{money(t.cost)}</b></div>
            <div class="card pf-card"><h4>{t.cost_complete ? "Lãi gộp" : "Lãi đã xác định"}</h4><b class={t.profit >= 0 ? "t-ok" : "t-danger"}>{money(t.profit)}</b></div>
            <div class="card pf-card"><h4>Số đơn</h4><b>{t.orders}</b><small>{t.returns || 0} phiếu trả</small></div>
          </div>
          <div class="card">
            <div class="ie-head">Sản phẩm đã mua (lãi dòng chưa phân bổ VAT/phí) <span class="ie-count">{data.products.length}</span></div>
            {!data.products.length ? <EmptyState>Không có đơn trong khoảng ngày.</EmptyState> : (
              <table class="inv-mini pf-table">
                <thead><tr><th>SP</th><th class="num">SL</th><th class="num">DT</th><th class="num">Lãi</th></tr></thead>
                <tbody>{data.products.map((p: any) => (
                  <tr key={p.code}>
                    <td><a href={`#/loi-nhuan/sp/${encodeURIComponent(p.code)}?${new URLSearchParams(range)}`}>{p.code}</a></td>
                    <td class="num">{fmtQty(p.qty)}</td>
                    <td class="num">{money(p.revenue)}</td>
                    <td class="num"><b class={p.profit >= 0 ? "t-ok" : "t-danger"}>{money(p.profit)}{p.missing_cost_lines > 0 ? " *" : ""}</b></td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          </div>
          <div class="card">
            <div class="ie-head">Lịch sử đơn hàng <span class="ie-count">{orders.length}</span></div>
            <table class="inv-mini pf-table">
              <thead><tr><th>Đơn / SP</th><th class="num">DT</th><th class="num">Vốn</th><th class="num">Lãi</th></tr></thead>
              <tbody>
                {orders.map((o: any) => (
                  <>
                    <tr key={o.thread_id} onClick={() => setOpen(open === o.thread_id ? null : o.thread_id)}>
                      <td><a href={o.kind === "return" ? `#/tra-hang/${o.return_id}` : `#/order/${o.thread_id}`} onClick={(e) => e.stopPropagation()}>{o.kind === "return" ? `Trả #${o.return_id}` : `#${o.thread_id}`}</a>
                        {" "}<span class="muted small">{o.date}</span>
                        <span class="pf-prod-chips">
                          {(o.items || []).slice(0, 5).map((it: any) => (
                            <span key={it.code} class={"pf-prod-chip" + (it.has_cost ? "" : " warn")}>
                              {it.code}<span class="q">×{fmtQty(it.qty)}</span>
                            </span>
                          ))}
                          {(o.items || []).length > 5 && <span class="pf-prod-chip">+{o.items.length - 5}</span>}
                        </span>
                      </td>
                      <td class="num">{money(o.revenue)}</td>
                      <td class="num">{money(o.cost)}</td>
                      <td class="num">{(o.items_with_cost > 0 || o.kind === "return")
                        ? <b class={o.profit >= 0 ? "t-ok" : "t-danger"}>{money(o.profit)}{o.cost_complete === false ? " *" : ""}</b>
                        : <span class="t-warn small">chưa có vốn</span>}</td>
                    </tr>
                    {open === o.thread_id && (
                      <tr class="pf-expand"><td colSpan={4}>
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
