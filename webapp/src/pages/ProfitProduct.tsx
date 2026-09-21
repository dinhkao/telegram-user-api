// Chi tiết LỢI NHUẬN 1 SP (#/loi-nhuan/sp/:code, office) ← GET /api/profit/product/{code}.
// Sửa GIÁ VỐN ngay tại trang (POST /api/profit/costs) + từng lần bán trong kỳ.
import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON, postJSON } from "../api";
import { money, fmtQty, parseMoney } from "../format";
import { initialProfitRange } from "../detail/profitDates";
import { ProfitDateBar, type DateRange } from "../detail/ProfitDateBar";
import { toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";
import { ProfitQualityNote, ProfitCoverageNote } from "../detail/ProfitOverview";
import { PageHead } from "../ui/PageHead";
import { Loading, ErrorState, EmptyState } from "../ui/states";

export function ProfitProduct({ code }: { code: string }) {
  const [range, setRange] = useState<DateRange>(() => initialProfitRange("this_month"));
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  const [cost, setCost] = useState<number>(0);
  const [busy, setBusy] = useState(false);
  const requestId = useRef(0);
  const load = () => {
    const id = ++requestId.current;
    setData(null); setErr("");
    getJSON(`/api/profit/product/${encodeURIComponent(code)}?since=${range.since}&until=${range.until}`, { cache: false })
      .then((j) => { if (id === requestId.current) { setData(j); setCost(j.product?.cost_price || 0); } })
      .catch((e: any) => { if (id === requestId.current) setErr(e?.message || "Lỗi tải"); });
  };
  useEffect(() => { load(); return () => { requestId.current++; }; }, [code, range.since, range.until]);
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
              {!data.product.cost_price && <span class="t-warn small">chưa nhập giá vốn hiện tại</span>}
            </div>
            <div class="muted small mt-1">Giá vốn hiện tại chỉ áp cho đơn mới. Đơn cũ thiếu giá vốn lịch sử cần đối chiếu và xác nhận riêng.</div>
          </div>
          <ProfitQualityNote t={t} /><ProfitCoverageNote coverage={data.coverage} />
          <p class="muted small">Giá vốn đã dự tính VAT bán ra. Lãi dòng SP chưa cộng VAT và phí cấp đơn; xem tổng đơn để có đủ các khoản này. Chưa trừ lãi vay và các chi phí vận hành khác.</p>
          <div class="pf-cards">
            <div class="card pf-card"><h4>SL bán − trả</h4><b>{fmtQty(t.qty)}</b></div>
            <div class="card pf-card"><h4>Doanh thu</h4><b>{money(t.revenue)}</b></div>
            <div class="card pf-card"><h4>Giá vốn</h4><b>{money(t.cost)}</b></div>
            <div class="card pf-card"><h4>{t.cost_complete ? "Lãi dòng" : "Lãi dòng đã xác định"}</h4><b class={t.profit >= 0 ? "t-ok" : "t-danger"}>{money(t.profit)}</b></div>
          </div>
          <div class="card">
            <div class="ie-head">Từng lần bán <span class="ie-count">{data.orders.length}</span></div>
            {!data.orders.length ? <EmptyState>Không có đơn trong khoảng ngày.</EmptyState> : (
              <table class="inv-mini pf-table">
                <thead><tr><th>Đơn / khách</th><th class="num">SL</th><th class="num">Giá bán</th><th class="num">Lãi</th></tr></thead>
                <tbody>{data.orders.map((o: any) => (
                  <tr key={`${o.thread_id}-${o.sell_price}`}>
                    <td><a href={o.kind === "return" ? `#/tra-hang/${o.return_id}` : `#/order/${o.thread_id}`}>{o.kind === "return" ? `Trả #${o.return_id}` : `#${o.thread_id}`}</a>
                      {" "}<span class="muted small">{o.date}</span><br />
                      <a href={`#/loi-nhuan/khach/${encodeURIComponent(o.customer)}?${new URLSearchParams(range)}`}>{o.customer}</a></td>
                    <td class="num">{fmtQty(o.qty)}</td>
                    <td class="num">{money(o.sell_price)}</td>
                    <td class="num">{o.has_cost
                      ? <b class={o.profit >= 0 ? "t-ok" : "t-danger"}>{money(o.profit)}{o.cost_complete === false ? " *" : ""}</b>
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
