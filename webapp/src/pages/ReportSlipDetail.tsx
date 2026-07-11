// Chi tiết PHIẾU BÁO CÁO SX (#/bao-cao/:id) — CHỈ văn phòng (tiền lương).
// Tự tính từ báo cáo thợ trong khoảng ngày: TỔNG CỘNG (SP + tiền) → THEO THỢ
// (tổng SP + tiền, bung theo mã SP) → TỪNG PHIẾU SX (ngày, SP, tiền — link phiếu).
// Data: getReportSlip. Xoá = admin. Realtime production/report_slips → tải lại.
import { useEffect, useState } from "preact/hooks";
import { currentUser, deleteReportSlip, getReportSlip, isOffice, soVN, type ReportSlip } from "../api";
import { onRealtime } from "../realtime";
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { toast, confirmDialog } from "../ui/feedback";

const dmy = (ymd: string) => (ymd && ymd.length >= 10 ? `${ymd.slice(8, 10)}/${ymd.slice(5, 7)}/${ymd.slice(0, 4)}` : ymd);
const dm = (ymd: string) => (ymd && ymd.length >= 10 ? `${ymd.slice(8, 10)}/${ymd.slice(5, 7)}` : ymd);
const money = (n: number) => soVN(Math.round(n)) + "đ";

export function ReportSlipDetail({ id }: { id: string }) {
  const [slip, setSlip] = useState<ReportSlip | null>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<Set<string>>(new Set());
  const admin = currentUser()?.role === "admin";

  const load = async () => {
    try { setSlip(await getReportSlip(id)); setErr(""); }
    catch (e: any) { setErr(e?.message || "Lỗi tải báo cáo"); }
  };
  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "production_changed" || e.type === "productions_changed" ||
          e.type === "report_slips_changed" || e.type === "resync") {
        clearTimeout(t); t = setTimeout(load, 500);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, [id]);

  const del = async () => {
    if (!slip) return;
    const ok = await confirmDialog(`Xoá phiếu báo cáo ${dmy(slip.from_ymd)} → ${dmy(slip.to_ymd)}? (số liệu SX không bị ảnh hưởng)`, { danger: true });
    if (!ok) return;
    try {
      await deleteReportSlip(slip.id);
      toast("Đã xoá phiếu báo cáo", "ok");
      window.location.hash = "#/bao-cao";
    } catch (e: any) {
      toast(e?.message || "Lỗi xoá", "err");
    }
  };

  const head = (
    <div class="wg-head">
      <BackLink fallback="#/bao-cao" />
      <div style={{ flex: 1 }}>
        <div class="wg-title"><Icon name="receipt" size={18} /> Báo cáo {slip ? `${dmy(slip.from_ymd)} → ${dmy(slip.to_ymd)}` : ""}</div>
        {slip && <div class="muted small">{slip.note ? `${slip.note} · ` : ""}{slip.created_by ? `tạo bởi ${slip.created_by}` : ""}</div>}
      </div>
      {admin && slip && (
        <button class="icon-btn rs-del" title="Xoá phiếu báo cáo" onClick={del}><Icon name="trash" size={18} /></button>
      )}
    </div>
  );

  if (!isOffice()) return <div class="rs-page">{head}<EmptyState icon="lock">Chỉ văn phòng được xem báo cáo.</EmptyState></div>;
  if (err) return <div class="rs-page">{head}<ErrorState msg={err} onRetry={load} /></div>;
  if (!slip || !slip.report) return <div class="rs-page">{head}<Loading /></div>;

  const rep = slip.report;
  const toggle = (k: string) => setOpen((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });

  return (
    <div class="rs-page">
      {head}

      <div class="wg-total">
        <div class="wg-total-money">{money(rep.totals.money)}</div>
        <div class="muted small">
          tổng cộng {soVN(rep.totals.cay)} SP · {rep.workers.length} thợ · {rep.phieus.length} phiếu SX
          {(rep.totals.allowance || 0) > 0 ? ` · gồm phụ cấp ${money(rep.totals.allowance)}` : ""}
        </div>
        {slip.worker_names && slip.worker_names.length > 0 && (
          <div class="muted small rs-only-workers">👤 Chỉ tính: <b>{slip.worker_names.join(", ")}</b></div>
        )}
      </div>

      {rep.missing_wage.length > 0 && (
        <div class="wg-warn">
          <Icon name="ban" size={15} /> Chưa có đơn giá lương cho: {rep.missing_wage.map((c, i) => <span key={c}>{i ? ", " : ""}<b>{c}</b></span>)} — số SP các mã này KHÔNG được tính tiền. <a href="#/luong-sp">Cài đơn giá →</a>
        </div>
      )}

      <section class="rs-sec">
        <div class="rs-sec-h"><Icon name="users" size={15} /> Theo thợ</div>
        {rep.workers.length === 0 ? (
          <EmptyState icon="check">Không có báo cáo thợ nào trong khoảng này.</EmptyState>
        ) : (
          <div class="wg-workers card rs-list">
            {rep.workers.map((w) => {
              const k = "w|" + w.name;
              const isOpen = open.has(k);
              return (
                <div class="wg-wk" key={k}>
                  <button class="wg-wk-row" onClick={() => toggle(k)} aria-expanded={isOpen}>
                    <Icon name={isOpen ? "chevronDown" : "chevronRight"} size={14} />
                    <span class="wg-wk-name">{w.name}</span>
                    {(w.allowance || 0) > 0 ? <span class="wg-wk-pc">+PC {money(w.allowance)}</span> : null}
                    <span class="wg-wk-cay muted small">{soVN(w.cay)} SP</span>
                    <span class="wg-wk-money">{money(w.money)}</span>
                  </button>
                  {isOpen && (
                    <div class="wg-items">
                      {w.items.map((it, i) => (
                        <div class="wg-item" key={i}>
                          <span class="wg-item-code">{it.code || "?"}</span>
                          <span class="wg-item-calc muted small">{soVN(it.cay)} SP × {soVN(it.wage)}đ</span>
                          <span class="wg-item-money">{money(it.money)}</span>
                        </div>
                      ))}
                      <a class="rs-wk-link" href={`#/sx-tho/${encodeURIComponent(w.name)}`}>Xem chi tiết thợ →</a>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section class="rs-sec">
        <div class="rs-sec-h"><Icon name="factory" size={15} /> Từng phiếu sản xuất</div>
        {rep.phieus.length === 0 ? (
          <EmptyState icon="check">Không có phiếu SX nào trong khoảng này.</EmptyState>
        ) : (
          <div class="card rs-list">
            {rep.phieus.map((p) => (
              <a class="rs-ph-row" key={p.thread_id} href={`#/san_xuat/${p.thread_id}`}>
                <span class="rs-ph-date">{dm(p.ymd)}</span>
                <span class="rs-ph-code">{p.codes.join(", ") || "?"}</span>
                <span class="muted small rs-ph-meta">{soVN(p.cay)} SP · {p.workers} thợ</span>
                <b class="rs-ph-money">{money(p.money)}</b>
              </a>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
