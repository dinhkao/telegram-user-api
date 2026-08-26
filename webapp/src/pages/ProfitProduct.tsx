// Chi tiết LỢI NHUẬN 1 SP (#/loi-nhuan/sp/:code, office) ← GET /api/profit/product/{code}.
// Sửa GIÁ VỐN ngay tại trang (POST /api/profit/costs) + từng lần bán trong kỳ.
import { useEffect, useState } from "preact/hooks";
import { getJSON, postJSON } from "../api";
import { money, fmtQty, parseMoney } from "../format";
import { ProfitDateBar, presetRange, type DateRange } from "../detail/ProfitDateBar";
import { toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { Loading, ErrorState, EmptyState } from "../ui/states";

export function ProfitProduct({ code }: { code: string }) {
  const [range, setRange] = useState<DateRange>(() => presetRange("this_month"));
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  const [cost, setCost] = useState<number>(0);
  const [busy, setBusy] = useState(false);
  const load = () => {
    setErr("");
    getJSON(`/api/profit/product/${encodeURIComponent(code)}?since=${range.since}&until=${range.until}`, { cache: false })
      .then((j) => { setData(j); setCost(j.product?.cost_price || 0); })
      .catch((e: any) => setErr(e?.message || "Lỗi tải"));
  };
  useEffect(load, [code, range.since, range.until]);
  const saveCost = async () => {
    setBusy(true);
    try {
      await postJSON("/api/profit/costs", { updates: { [code.toUpperCase()]: cost } });
      toast("Đã lưu giá vốn", "ok");
      load();
    } catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); }
    finally { setBusy(false); }
  };
  if (err && !data) return <div class="prod-detail"><PageHead fallback="#/loi-nhuan" title={code} /><ErrorState msg={err} onRetry={load} /></div>;
  const t = data?.totals;
  return (
    <div class="prod-detail">
      <PageHead fallback="#/loi-nhuan" title={code} sub={data?.product?.name || "Lợi nhuận sản phẩm"}
        right={<a class="btn small" href={`#/kho/${encodeURIComponent(code)}`}>Trang SP</a>} />
      <ProfitDateBar range={range} onChange={setRange} />
      {!data ? <Loading /> : (
        <>
          <div class="card">
            <div class="ie-head">Giá vốn</div>
            <div class="row">
              <input class="note-inp" style="max-width:140px" inputMode="numeric"
                value={cost ? money(cost) : ""} placeholder="giá vốn"
                onInput={(e: any) => setCost(parseMoney(e.target.value))} />
              <button class="btn small primary" disabled={busy} onClick={saveCost}>
                <Icon name="save" size={14} /> Lưu
              </button>
              {!data.product.cost_price && <span class="t-warn small">chưa có giá vốn — lãi đang tính 0</span>}
            </div>
            <div class="muted small mt-1">Giá vốn ĐÃ chốt vào đơn cũ không đổi (snapshot) — chỉ áp cho đơn mới/đơn chưa đóng băng.</div>
          </div>
          <div class="pf-cards">
            <div class="card pf-card"><h4>SL bán</h4><b>{fmtQty(t.qty)}</b></div>
            <div class="card pf-card"><h4>Doanh thu</h4><b>{money(t.revenue)}</b></div>
            <div class="card pf-card"><h4>Giá vốn</h4><b>{money(t.cost)}</b></div>
            <div class="card pf-card"><h4>Lãi</h4><b class={t.profit >= 0 ? "t-ok" : "t-danger"}>{money(t.profit)}</b></div>
          </div>
          <div class="card">
            <div class="ie-head">Từng lần bán <span class="ie-count">{data.orders.length}</span></div>
            {!data.orders.length ? <EmptyState>Không có đơn trong khoảng ngày.</EmptyState> : (
              <table class="inv-mini pf-table">
                <thead><tr><th>Đơn / khách</th><th class="num">SL</th><th class="num">Giá bán</th><th class="num">Lãi</th></tr></thead>
                <tbody>{data.orders.map((o: any) => (
                  <tr key={`${o.thread_id}-${o.sell_price}`}>
                    <td><a href={`#/order/${o.thread_id}`}>#{o.thread_id}</a>
                      {" "}<span class="muted small">{o.date}</span><br />
                      <a href={`#/loi-nhuan/khach/${encodeURIComponent(o.customer)}`}>{o.customer}</a></td>
                    <td class="num">{fmtQty(o.qty)}</td>
                    <td class="num">{money(o.sell_price)}</td>
                    <td class="num">{o.has_cost
                      ? <b class={o.profit >= 0 ? "t-ok" : "t-danger"}>{money(o.profit)}</b>
                      : <span class="t-warn small">chưa có vốn</span>}</td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}
