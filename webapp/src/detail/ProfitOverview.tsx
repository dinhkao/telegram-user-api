import { money, fmtQty } from "../format";
import { Chg } from "./ProfitDateBar";
import { displayRange, type DateRange } from "./profitDates";
import type { ProfitFilters } from "./profitFilters";
const pct = (v: number | null | undefined) => v == null ? "—" : `${v.toFixed(1)}%`;

export function ProfitCoverageNote({ coverage }: { coverage: any }) {
  if (!coverage?.quality_errors) return null;
  const parts = [
    [coverage.invalid_orders, "đơn lỗi"], [coverage.undated_orders, "đơn thiếu ngày"],
    [coverage.invalid_returns, "phiếu trả lỗi"], [coverage.undated_returns, "phiếu trả thiếu ngày"],
    [coverage.return_amount_mismatches, "phiếu trả lệch tổng tiền"],
  ].filter(([count]) => count > 0).map(([count, label]) => `${count} ${label}`);
  return <div class="pf-data-warning" role="alert"><b>Cần đối chiếu dữ liệu:</b> {parts.join(", ")} trong lịch sử hệ thống.
    {coverage.undated_orders > 0 && <> Các đơn thiếu ngày chưa thể xác định thuộc kỳ nào: {(coverage.undated_order_ids || []).slice(0, 20).map((id: number) => <a href={`#/order/${id}`}> #{id} </a>)}</>}
    {coverage.invalid_orders > 0 && <> Đơn lỗi: {(coverage.invalid_order_ids || []).slice(0, 20).map((id: number) => <a href={`#/order/${id}`}> #{id} </a>)}</>}
  </div>;
}

export function ProfitQualityNote({ t }: { t: any }) {
  return <>
    {t?.missing_cost_lines > 0 && <div class="pf-data-warning" role="note"><b>{t.missing_cost_lines} dòng chưa đủ căn cứ giá vốn.</b> Lãi hiển thị là phần đã xác định, chưa phải lãi đầy đủ. {t.missing_cost_revenue > 0 && <>Doanh thu bán hàng chưa tính được lãi: {money(t.missing_cost_revenue)}. </>}{t.missing_cost_returns > 0 && <>{t.missing_cost_returns} phiếu trả chưa xử lý xong hàng hoặc thiếu vốn lịch sử để hoàn vốn.</>}</div>}
  </>;
}

export function ProfitSummary({ s }: { s: any }) {
  const afterLoan = s.real_profit != null;
  const result = afterLoan ? s.real_profit : s.profit;
  return <>
    <div class={"card pf-result" + (result < 0 ? " negative" : "")}>
      <div class="pf-result-head"><span>{afterLoan ? "LÃI SAU LÃI VAY" : "LÃI GỘP NHÓM ĐANG LỌC"} · {s.cost_complete ? "ƯỚC TÍNH" : "PHẦN ĐÃ XÁC ĐỊNH"} (ĐỒNG)</span><span>{!s.entries ? "Chưa có giao dịch" : s.cost_complete ? "Đủ căn cứ giá vốn" : "Chưa đủ giá vốn"}</span></div>
      <div class="pf-result-value">{money(result)}</div>
      <div class="pf-result-comparison"><Chg v={afterLoan ? s.changes?.real_profit : s.changes?.profit} nullLabel="Chưa đủ cơ sở so sánh lãi" /></div>
      <div class="pf-result-breakdown"><span>Lãi gộp đã xác định <b>{money(s.profit)}</b></span>{afterLoan && <span>Lãi vay kỳ này <b>−{money(s.loan)}</b></span>}<span>{afterLoan ? "Biên sau vay" : "Biên gộp"} <b>{pct(afterLoan ? s.margin : s.gross_margin)}</b></span></div>
    </div>
    <div class="pf-cards pf-summary-cards">
      <div class="card pf-card"><h4>Doanh thu chưa VAT</h4><b>{money(s.revenue)}</b><Chg v={s.changes?.revenue} nullLabel="Chưa đủ cơ sở so sánh" /><span class="muted small">Đã giảm {money(s.returns_revenue)} hàng trả</span></div>
      <div class="card pf-card"><h4>{s.cost_complete ? "Lãi gộp" : "Lãi đã xác định"}</h4><b class={s.profit >= 0 ? "t-ok" : "t-danger"}>{money(s.profit)}</b><Chg v={s.changes?.profit} nullLabel="Chưa đủ cơ sở so sánh lãi" /><span class="muted small">{s.avg_order_profit == null ? "Chưa tính lãi TB khi thiếu vốn" : `TB ${money(s.avg_order_profit)} / đơn bán`}</span></div>
      <div class="card pf-card"><h4>Đơn bán</h4><b>{s.orders}</b><Chg v={s.changes?.orders} nullLabel="Chưa đủ cơ sở so sánh" /><span class="muted small">{s.returns} phiếu trả · {s.customers} khách · {s.products} mã SP</span></div>
      <div class="card pf-card"><h4>Biên lãi gộp</h4><b>{pct(s.gross_margin)}</b><span class={"pf-chg " + (s.margin_change == null || s.margin_change === 0 ? "new" : s.margin_change > 0 ? "up" : "down")}>
        {s.margin_change == null ? "Chưa đủ dữ liệu so sánh" : `${s.margin_change > 0 ? "+" : ""}${s.margin_change.toFixed(1)} điểm %`}</span><span class="muted small">Giá vốn đã xác định {money(s.cost)}</span></div>
    </div>
    <p class="pf-comparison-note">Giá vốn đã tính sẵn VAT bán ra. Lãi tính từ tổng tiền khách thanh toán gồm VAT trừ giá vốn này.</p>
    <p class="pf-comparison-note">So với {s.prev_label || "kỳ trước"} · Cùng số ngày và bộ lọc. Chưa trừ hết chi phí vận hành.</p>
    <ProfitQualityNote t={s} />
    {s.filtered && <div class="pf-data-warning" role="note">Nhóm đang lọc chỉ hiển thị lãi gộp. Lãi vay toàn doanh nghiệp trong kỳ là {money(s.company_loan)}, chưa có quy tắc phân bổ riêng cho nhóm.</div>}
    {s.sales_only_filter && <div class="pf-data-warning" role="note">Bộ lọc thanh toán hoặc mức lãi chỉ xét đơn bán; phiếu trả không tham gia nhóm này. Bỏ các bộ lọc đó để xem doanh thu sau trả hàng.</div>}
  </>;
}

export function ProfitOverview({ data, range, onFilter }: { data: any; range: DateRange; onFilter: (f: Partial<ProfitFilters>) => void }) {
  const s = data.summary;
  const leading = [...data.top_customers].sort((a: any, b: any) => b.revenue - a.revenue)[0];
  const insightRows = [
    { label: "Đơn đang lỗ", count: s.loss_orders, text: `${money(s.loss_total)} tổng lỗ · chỉ đơn đủ giá vốn`, filter: { profitability: "loss" }, tone: "danger" },
    { label: "Biên lãi dưới 10%", count: s.low_margin_orders, text: "Biên từ 0 đến dưới 10% · chỉ đơn đủ giá vốn", filter: { profitability: "low_margin" }, tone: "warn" },
    { label: "Thiếu giá vốn", count: s.missing_cost_orders, text: `${s.missing_cost_lines} dòng SP · ${money(s.missing_cost_revenue)} doanh thu`, filter: { cost_status: "missing" }, tone: "warn" },
    { label: "Chưa có phiếu thu", count: s.unreceived_orders, text: "Chưa có bản ghi thanh toán trong đơn", filter: { payment: "unreceived" }, tone: "neutral" },
  ];
  const drill = (path: string) => `${path}?${new URLSearchParams(range)}`;
  return <>
    <div class="card pf-insights"><div class="ie-head">Điểm cần xem <span class="muted small">Trong bộ lọc hiện tại</span></div>
      <div class="pf-insight-grid">{insightRows.map(item => <button class={`pf-insight ${item.tone}`} disabled={!item.count}
        onClick={() => onFilter(item.filter)}><span>{item.label} <b>{item.count} đơn</b></span><small>{item.text}</small>{item.count > 0 && <em>Xem các đơn này →</em>}</button>)}</div>
    </div>
    <div class="card pf-detail-metrics"><div class="ie-head">Hiệu quả & dữ liệu</div>
      <dl><div><dt>Ngày có đơn</dt><dd>{s.active_days} / {s.period_days} ngày</dd></div><div><dt>Độ phủ giá vốn (theo dòng SP)</dt><dd>{pct(s.cost_coverage)}</dd></div>
        <div><dt>Đơn có phiếu thu</dt><dd>{s.received_orders} / {s.orders}</dd></div><div><dt>Doanh thu TB / ngày của kỳ</dt><dd>{money(s.period_days ? Math.round(s.revenue / s.period_days) : 0)}</dd></div></dl>
      {leading && leading.revenue_share >= 40 && <p class="pf-concentration"><b>{leading.name}</b> chiếm {pct(leading.revenue_share)} doanh thu trong bộ lọc này.</p>}
    </div>
    <div class="pf-tops">{["customers", "products"].map(kind => <div class="card">
      <div class="ie-head">{kind === "customers" ? "Top khách theo lãi đã xác định" : "Top SP theo lãi đã xác định"}</div>
      <p class="small muted">Cùng kỳ và bộ lọc đang chọn{kind === "products" ? " · Lãi dòng chưa phân bổ VAT và phí cấp đơn" : ""}</p>
      {(data[`top_${kind}`] || []).length === 0 && <p class="muted small">Không có dữ liệu phù hợp.</p>}
      {(data[`top_${kind}`] || []).map((row: any, i: number) => <a class="pf-top-row" href={drill(kind === "customers" ? `#/loi-nhuan/khach/${encodeURIComponent(row.name)}` : `#/loi-nhuan/sp/${encodeURIComponent(row.code)}`)}>
        <span class="pf-rank">{i + 1}</span><span class="pf-top-info"><b>{kind === "customers" ? row.name : row.code}</b><small>DT {money(row.revenue)} · {kind === "customers" ? `${row.orders} đơn` : `SL ${fmtQty(row.qty)}`}</small></span>
        <span class="num"><b class={row.profit >= 0 ? "t-ok" : "t-danger"}>{money(row.profit)}</b><small>Biên {pct(row.margin)}{row.missing_cost_lines > 0 || row.missing_cost_orders > 0 ? " *" : ""}</small>{(row.missing_cost_lines > 0 || row.missing_cost_orders > 0) && <small class="t-warn">Lãi chưa đầy đủ</small>}</span>
      </a>)}
    </div>)}</div>
    <details class="card pf-method"><summary>Cách đọc & chi tiết phép tính</summary>
      <p>Kỳ đang xem: {displayRange(range)}. Các bộ lọc chọn toàn đơn; lọc mã SP vẫn tính cả sản phẩm khác và phí trong đơn chứa mã đó.</p>
      <p>Doanh thu = tiền hàng + phí vận chuyển thu khách − chiết khấu − hàng trả đã xác nhận. VAT bán ra được tách riêng khỏi doanh thu và có trong tổng tiền khách thanh toán. Vì giá vốn đã dự tính khoản VAT bán ra phải chịu, phép tính lãi vẫn cộng VAT thực thu ở cấp đơn.</p>
      <dl><div><dt>Tổng tiền khách thanh toán (gồm VAT, sau trả hàng)</dt><dd>{money(s.customer_total)}</dd></div><div><dt>VAT bán ra thu khách</dt><dd>{money(s.fees.vat)}</dd></div><div><dt>Phí vận chuyển thu khách</dt><dd>{money(s.fees.pvc)}</dd></div><div><dt>Chi phí giao hàng đã ghi</dt><dd>{money(s.fees.shipping_cost)}</dd></div><div><dt>Chiết khấu</dt><dd>−{money(s.fees.discount)}</dd></div><div><dt>Giảm doanh thu trả hàng</dt><dd>−{money(s.returns_revenue)}</dd></div></dl>
      <p>Lãi đã xác định = lãi các dòng có vốn lịch sử + VAT bán ra thu khách + phí vận chuyển thu khách − chiết khấu − chi phí giao hàng đã ghi + điều chỉnh trả hàng. Dòng bán thiếu vốn chưa tính lãi và không được coi là hòa vốn. Biên và tăng trưởng lãi chỉ hiện khi đủ căn cứ giá vốn.</p>
      <p>Phiếu trả chỉ tính khi đã gắn hóa đơn KiotViet, theo ngày tạo phiếu và kết quả xử lý hàng hiện có. Hàng hủy không hoàn vốn; hàng nhập lại kho chỉ hoàn vốn khi đối chiếu được giá vốn lịch sử. Phiếu chưa xử lý xong vẫn giảm doanh thu và cảnh báo phần vốn chưa xác định.</p>
      <p>Lãi sau lãi vay chỉ tính cho toàn bộ doanh nghiệp = lãi gộp − lãi vay theo ngày và trọng số tháng. Chưa trừ các chi phí vận hành khác. Bảng sản phẩm tính lãi dòng trước khi cộng VAT và điều chỉnh phí cấp đơn; chưa phân bổ các khoản này cho từng SP.</p>
      {s.shipping_cost_unrecorded_orders > 0 && <p class="t-warn">{s.shipping_cost_unrecorded_orders} đơn có thu phí vận chuyển nhưng chưa ghi chi phí giao hàng riêng; phần lãi này có thể chưa trừ đủ chi phí giao hàng.</p>}
      <p>“Có phiếu thu” gồm cả thu một phần. Ngày báo cáo là ngày tạo đơn theo giờ Việt Nam. Đã lấy toàn bộ lịch sử có trong hệ thống, không giới hạn theo số đơn. Ngày đơn sớm nhất: {data.coverage?.first_order_date || "chưa có"}; mới nhất: {data.coverage?.last_order_date || "chưa có"}. Kỳ này gồm {data.coverage?.legacy_orders_included || 0} đơn trước mốc cũ.</p>
      <p>Tỷ lệ thay đổi = (kỳ này − kỳ trước) / trị tuyệt đối kỳ trước. Chỉ số biên so sánh theo điểm phần trăm. Khi kỳ trước bằng 0 và kỳ này khác 0, không hiển thị phần trăm tăng trưởng.</p>
    </details>
  </>;
}
