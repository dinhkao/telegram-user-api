// Báo cáo sản xuất theo thợ — phần XEM ở trang chi tiết. Khi có người SỬA (giữ khoá):
// nút "Sửa" bị CHẶN, đổi thành "<người> đang nhập…" (mờ, bấm → toast) giống khoá chọn
// thùng; bảng UPDATE TRỰC TIẾP theo bản nháp (report_draft) để người ngoài xem realtime.
// Khoá/nháp: server_app/production_routes.py. Tính mâm/tổng: detail/reportCalc.
import { useEffect, useState } from "preact/hooks";
import { soVN, isOffice, currentUser, reportLockStatus, type ProdSlip, type ProdReport } from "../api";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { toast } from "../ui/feedback";
import { draftToRows, type Wrow } from "./reportCalc";
import { ProductionWages } from "./ProductionWages";

export function ProductionReport({ threadId, slip, locked }: { threadId: string; slip: ProdSlip; locked?: boolean }) {
  const rep = slip.bang as ProdReport | null;
  const [editor, setEditor] = useState<string | null>(null);            // tên người đang giữ khoá sửa
  const [draft, setDraft] = useState<{ rows: Wrow[]; date?: string; start?: string; end?: string } | null>(null);
  useEffect(() => {
    let alive = true;
    setDraft(null);
    const syncEditor = () => reportLockStatus(threadId).then((holder) => {
      if (!alive) return;
      setEditor(holder);
      if (!holder) setDraft(null);
    }).catch(() => {});
    syncEditor();
    // Fallback khi request unlock/event realtime bị rớt: sau khi TTL server hết hạn,
    // badge vẫn tự biến mất thay vì kẹt tên người sửa cho tới lần reload sau.
    const poll = setInterval(syncEditor, 15000);
    const offRealtime = onRealtime((e) => {
      if (e.type === "report_lock" && e.thread_id === String(threadId)) {
        setEditor(e.holder || null);
        if (!e.holder) setDraft(null);   // hết người sửa → bảng về bản ĐÃ LƯU
      } else if (e.type === "report_draft" && e.thread_id === String(threadId)) {
        const d: any = e.draft || {};
        setDraft({ rows: Array.isArray(d.rows) ? d.rows : [], date: d.date, start: d.start, end: d.end });
        if (d.by) setEditor((cur) => cur || d.by);
      }
    });
    return () => { alive = false; clearInterval(poll); offRealtime(); };
  }, [threadId]);

  const me = currentUser()?.display_name || currentUser()?.username || "";
  const heldByOther = !!editor && editor !== me;
  const scm = Number(rep?.so_cay_1_mam || slip.sp_mam || 0);
  const liveRows = (draft ? draftToRows(draft.rows, scm) : (rep?.rows || []))
    .filter((r) => (r.name || "").trim() !== "" || (r.tong_calc || 0) > 0);
  const grand = draft ? Math.round(liveRows.reduce((s, r) => s + (r.tong_calc || 0), 0) * 100) / 100 : (rep?.grand_total || 0);
  const mDate = draft?.date || rep?.date, mStart = draft?.start || rep?.start, mEnd = draft?.end || rep?.end;

  return (
    <section class="card">
      <div class="row space" style={{ alignItems: "center", marginBottom: "8px" }}>
        <label class="card-label" style={{ margin: 0 }}><Icon name="chart" size={16} /> Báo cáo theo thợ</label>
        {locked
          ? <span class="muted small"><Icon name="lock" size={13} /> đã khoá</span>
          : heldByOther
            ? <button class="btn small faded wr-editing" onClick={() => toast(`${editor} đang nhập báo cáo — chờ họ xong`, "info")}>
                <Icon name="edit" size={15} /> {editor} đang nhập…
              </button>
            : <a class="btn primary small" href={`#/san_xuat/${threadId}/bao-cao`}><Icon name="edit" size={16} /> Sửa</a>}
      </div>

      {liveRows.length > 0 ? (
        <>
          <div class="prod-report-meta">
            {rep?.product_code && <span><Icon name="box" size={14} /> {rep.product_code}</span>}
            {rep && rep.so_cay_1_mam > 0 && <span>🌿 {rep.so_cay_1_mam}/mâm</span>}
            {mDate && <span><Icon name="calendar" size={14} /> {mDate}</span>}
            {mStart && mEnd && <span><Icon name="clock" size={14} /> {mStart}–{mEnd}</span>}
            <span>· Tổng <b>{soVN(grand)}</b></span>
            {draft && <span class="wr-live"><i class="wr-live-dot" /> đang nhập trực tiếp</span>}
          </div>
          <div class="prod-report-scroll">
            <table class="prod-report-table">
              <thead>
                <tr><th>Thợ</th><th>Gạch</th><th>Trừ</th><th>Lẻ</th><th>Mâm</th><th>Tổng SP</th><th>Ghi chú</th></tr>
              </thead>
              <tbody>
                {liveRows.map((r, i) => (
                  <tr key={i} class={r.tong_calc > 0 ? "" : "prod-row-off"}>
                    <td>{r.name ? <a class="wr-tho-link" href={`#/sx-tho/${encodeURIComponent(r.name)}`}>{r.name}</a> : ""}</td>
                    <td>{soVN(r.so_gach)}</td>
                    <td>{soVN(r.so_tru)}</td>
                    <td>{soVN(r.so_cay_le)}</td>
                    <td class={r.mam_de != null ? "wr-ovr" : ""} title={r.mam_de != null ? "Mâm đè" : undefined}>{soVN(r.so_mam)}</td>
                    <td class={"strong" + (r.sp_de != null ? " wr-ovr" : "")} title={r.sp_de != null ? "SP đè" : undefined}>{soVN(r.tong_calc)}</td>
                    <td>{r.note || ""}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr><td colSpan={5}>TỔNG CỘNG</td><td class="strong">{soVN(grand)}</td><td></td></tr>
              </tfoot>
            </table>
          </div>
          {isOffice() && !draft && <ProductionWages threadId={threadId} workers={liveRows.map((r) => ({ name: r.name, cay: r.tong_calc }))} />}
        </>
      ) : (
        <p class="muted small">Chưa có báo cáo. Bấm <b>✏️ Sửa</b> để nhập trực tiếp.</p>
      )}
    </section>
  );
}
