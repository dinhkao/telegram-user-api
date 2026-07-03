// Báo cáo sản xuất theo thợ — dán dữ liệu ; từ Google Sheet, xem trước (parse
// phía server) rồi Lưu. Server tính tổng theo công thức (số cây 1 mâm) và ghi vào
// slip.bang. Hiển thị báo cáo đã lưu sẵn nếu có.
import { useState } from "preact/hooks";
import { parseProductionReport, saveProductionReport, soVN, type ProdSlip, type ProdReport } from "../api";

export function ProductionReport({ threadId, slip }: { threadId: string; slip: ProdSlip }) {
  const [text, setText] = useState("");
  const [report, setReport] = useState<ProdReport | null>((slip.bang as ProdReport) || null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [open, setOpen] = useState(false);

  const preview = async () => {
    if (!text.trim()) return;
    setBusy(true);
    setMsg("");
    try {
      const r = await parseProductionReport(threadId, text);
      setReport(r);
      if (!r.rows?.length) setMsg("Không phân tích được dữ liệu — kiểm tra định dạng.");
    } catch (e: any) {
      setMsg(e?.message || "Lỗi phân tích");
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (!text.trim()) return;
    setBusy(true);
    setMsg("");
    try {
      const r = await saveProductionReport(threadId, text);
      setReport(r);
      setMsg("✅ Đã lưu báo cáo");
    } catch (e: any) {
      setMsg(e?.message || "Lỗi lưu báo cáo");
    } finally {
      setBusy(false);
    }
  };

  const makers = report ? report.rows.filter((r) => r.tong_calc > 0).sort((a, b) => b.tong_calc - a.tong_calc) : [];

  return (
    <section class="card">
      <label class="card-label" onClick={() => setOpen((v) => !v)} style={{ cursor: "pointer" }}>
        📊 Báo cáo theo thợ {open ? "▲" : "▼"}
      </label>

      {open && (
        <>
          <textarea
            class="prod-report-input"
            rows={5}
            value={text}
            onInput={(e) => setText((e.target as HTMLTextAreaElement).value)}
            placeholder="Dán dữ liệu từ Google Sheet (mỗi thợ 1 dòng, ngăn bởi dấu ;)…"
          />
          <div class="row">
            <button class="btn" disabled={busy} onClick={preview}>
              👁 Xem trước
            </button>
            <button class="btn primary" disabled={busy} onClick={save}>
              💾 Lưu báo cáo
            </button>
          </div>
          {msg && <div class="muted small">{msg}</div>}
        </>
      )}

      {report && report.rows?.length > 0 && (
        <div class="prod-report-out">
          <div class="prod-report-meta">
            {report.product_code && <span>📦 {report.product_code}</span>}
            {report.so_cay_1_mam > 0 && <span>🌿 {report.so_cay_1_mam}/mâm</span>}
            {report.date && <span>📅 {report.date}</span>}
            {report.start && report.end && (
              <span>
                🕒 {report.start}–{report.end}
              </span>
            )}
          </div>
          <div class="prod-report-scroll">
            <table class="prod-report-table">
              <thead>
                <tr>
                  <th>Thợ</th>
                  <th>Gạch</th>
                  <th>Trừ</th>
                  <th>Lẻ</th>
                  <th>Mâm</th>
                  <th>Tổng SP</th>
                </tr>
              </thead>
              <tbody>
                {makers.map((r, i) => (
                  <tr key={i}>
                    <td>{r.name}</td>
                    <td>{soVN(r.so_gach)}</td>
                    <td>{soVN(r.so_tru)}</td>
                    <td>{soVN(r.so_cay_le)}</td>
                    <td>{soVN(r.so_mam)}</td>
                    <td class="strong">{soVN(r.tong_calc)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={5}>TỔNG CỘNG</td>
                  <td class="strong">{soVN(report.grand_total)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
