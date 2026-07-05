// Báo cáo sản xuất theo thợ — CHỈ XEM ở trang chi tiết, LUÔN hiện (không thu gọn).
// Sửa → trang riêng (#/san_xuat/:id/bao-cao, ProductionReportEdit) khoá 1 người sửa.
import { soVN, type ProdSlip, type ProdReport } from "../api";

export function ProductionReport({ threadId, slip }: { threadId: string; slip: ProdSlip }) {
  const rep = slip.bang as ProdReport | null;
  const rows = rep?.rows || [];

  return (
    <section class="card">
      <div class="row space" style={{ alignItems: "center", marginBottom: "8px" }}>
        <label class="card-label" style={{ margin: 0 }}>📊 Báo cáo theo thợ</label>
        <a class="btn primary small" href={`#/san_xuat/${threadId}/bao-cao`}>✏️ Sửa</a>
      </div>

      {rows.length > 0 ? (
        <>
          <div class="prod-report-meta">
            {rep?.product_code && <span>📦 {rep.product_code}</span>}
            {rep && rep.so_cay_1_mam > 0 && <span>🌿 {rep.so_cay_1_mam}/mâm</span>}
            {rep?.date && <span>📅 {rep.date}</span>}
            {rep?.start && rep?.end && <span>🕒 {rep.start}–{rep.end}</span>}
            <span>· Tổng <b>{soVN(rep!.grand_total)}</b></span>
          </div>
          <div class="prod-report-scroll">
            <table class="prod-report-table">
              <thead>
                <tr><th>Thợ</th><th>Gạch</th><th>Trừ</th><th>Lẻ</th><th>Mâm</th><th>Tổng SP</th><th>Ghi chú</th></tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} class={r.tong_calc > 0 ? "" : "prod-row-off"}>
                    <td>{r.name ? <a class="wr-tho-link" href={`#/sx-tho/${encodeURIComponent(r.name)}`}>{r.name}</a> : ""}</td>
                    <td>{soVN(r.so_gach)}</td>
                    <td>{soVN(r.so_tru)}</td>
                    <td>{soVN(r.so_cay_le)}</td>
                    <td>{soVN(r.so_mam)}</td>
                    <td class="strong">{soVN(r.tong_calc)}</td>
                    <td>{r.note || ""}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr><td colSpan={5}>TỔNG CỘNG</td><td class="strong">{soVN(rep!.grand_total)}</td><td></td></tr>
              </tfoot>
            </table>
          </div>
        </>
      ) : (
        <p class="muted small">Chưa có báo cáo. Bấm <b>✏️ Sửa</b> để nhập trực tiếp.</p>
      )}
    </section>
  );
}
