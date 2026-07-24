// Chi tiết PHIẾU BÁO CÁO SX (#/bao-cao/:id) — CHỈ văn phòng (tiền lương).
// Tự tính từ báo cáo thợ trong khoảng ngày: TỔNG CỘNG (SP + tiền) → THEO THỢ
// (tổng SP + tiền, bung theo mã SP) → TỪNG PHIẾU SX (ngày, SP, tiền — link phiếu).
// ✏️ Sửa (văn phòng): đổi ngày/ghi chú/chọn thợ → báo cáo tính lại ngay.
// Data: getReportSlip/updateReportSlip. Xoá = admin. Realtime → tải lại.
import { useEffect, useState } from "preact/hooks";
import { currentUser, deleteReportSlip, getReportSlip, isOffice, listWorkers, soVN, updateReportSlip, type ReportSlip, type Worker } from "../api";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { toast, confirmDialog } from "../ui/feedback";
import { WorkerChips } from "../detail/WorkerChips";

const dmy = (ymd: string) => (ymd && ymd.length >= 10 ? `${ymd.slice(8, 10)}/${ymd.slice(5, 7)}/${ymd.slice(0, 4)}` : ymd);
const dm = (ymd: string) => (ymd && ymd.length >= 10 ? `${ymd.slice(8, 10)}/${ymd.slice(5, 7)}` : ymd);
const money = (n: number) => soVN(Math.round(n)) + "đ";
// "7:00" / "7h" / "7" → "07:00"; giữ nguyên nếu không parse được
const hhmm = (s: string) => {
  const m = String(s || "").trim().match(/^(\d{1,2})(?:[:hg.](\d{1,2})?)?$/i);
  if (!m) return s;
  const h = m[1].padStart(2, "0"), mi = (m[2] || "0").padStart(2, "0");
  return `${h}:${mi}`;
};

export function ReportSlipDetail({ id }: { id: string }) {
  const [slip, setSlip] = useState<ReportSlip | null>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<Set<string>>(new Set());
  const admin = currentUser()?.role === "admin";
  // ── sửa phiếu ──
  const [editing, setEditing] = useState(false);
  const [eFrom, setEFrom] = useState("");
  const [eTo, setETo] = useState("");
  const [eNote, setENote] = useState("");
  const [eSel, setESel] = useState<Set<number> | null>(null);
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [saving, setSaving] = useState(false);

  const startEdit = () => {
    if (!slip) return;
    setEFrom(slip.from_ymd); setETo(slip.to_ymd); setENote(slip.note || "");
    setESel(slip.worker_ids && slip.worker_ids.length ? new Set(slip.worker_ids) : null);
    listWorkers().then(({ workers }) => setWorkers(workers)).catch(() => {});
    setEditing(true);
  };

  const saveEdit = async () => {
    if (!slip || saving) return;
    if (!eFrom || !eTo) { toast("Phải chọn ngày bắt đầu và ngày kết thúc", "err"); return; }
    if (eFrom > eTo) { toast("Ngày bắt đầu phải trước ngày kết thúc", "err"); return; }
    if (eSel !== null && eSel.size === 0) { toast("Chọn ít nhất 1 thợ", "err"); return; }
    setSaving(true);
    try {
      await updateReportSlip(slip.id, { from: eFrom, to: eTo, note: eNote, worker_ids: eSel === null ? null : [...eSel] });
      toast("Đã lưu phiếu báo cáo", "ok");
      setEditing(false);
      load();
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu", "err");
    } finally {
      setSaving(false);
    }
  };

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
    <PageHead fallback="#/bao-cao"
      title={<><Icon name="receipt" size={18} /> Báo cáo {slip ? `${dmy(slip.from_ymd)} → ${dmy(slip.to_ymd)}` : ""}</>}
      sub={slip ? `${slip.note ? `${slip.note} · ` : ""}${slip.created_by ? `tạo bởi ${slip.created_by}` : ""}` : undefined}
      right={slip ? (
        <>
          <button class="icon-btn" title="Sửa phiếu báo cáo" onClick={startEdit}><Icon name="edit" size={18} /></button>
          {admin && <button class="icon-btn rs-del" title="Xoá phiếu báo cáo" onClick={del}><Icon name="trash" size={18} /></button>}
        </>
      ) : undefined} />
  );

  if (!isOffice()) return <div class="rs-page">{head}<EmptyState icon="🔒">Chỉ văn phòng được xem báo cáo.</EmptyState></div>;
  if (err) return <div class="rs-page">{head}<ErrorState msg={err} onRetry={load} /></div>;
  if (!slip || !slip.report) return <div class="rs-page">{head}<Loading /></div>;

  const rep = slip.report;
  const toggle = (k: string) => setOpen((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });

  return (
    <div class="rs-page">
      {head}

      {editing && (
        <section class="card rs-create">
          <label class="card-label"><Icon name="edit" size={15} /> Sửa phiếu báo cáo</label>
          <div class="rs-dates">
            <label class="rs-date-f">
              <span class="muted small">Từ ngày</span>
              <input type="date" value={eFrom} max={eTo || undefined} onChange={(e: any) => setEFrom(e.currentTarget.value)} />
            </label>
            <label class="rs-date-f">
              <span class="muted small">Đến ngày</span>
              <input type="date" value={eTo} min={eFrom || undefined} onChange={(e: any) => setETo(e.currentTarget.value)} />
            </label>
          </div>
          <WorkerChips workers={workers} value={eSel} onChange={setESel} />
          <input class="rs-note" type="text" placeholder="Ghi chú (tuỳ chọn)…" value={eNote}
            onInput={(e: any) => setENote(e.currentTarget.value)} />
          <div class="rs-edit-btns">
            <button class="btn small" disabled={saving} onClick={() => setEditing(false)}>Huỷ</button>
            <button class="btn small primary" disabled={saving} onClick={saveEdit}>{saving ? "Đang lưu…" : "Lưu"}</button>
          </div>
        </section>
      )}

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

      {(() => {
        // "giờ: <tên thợ>" = thiếu TIỀN 1 GIỜ (đặt ở trang thợ) ≠ thiếu đơn giá SP
        const spMiss = rep.missing_wage.filter((c) => !c.startsWith("giờ: "));
        const gioMiss = rep.missing_wage.filter((c) => c.startsWith("giờ: ")).map((c) => c.slice(5));
        return (
          <>
            {spMiss.length > 0 && (
              <div class="wg-warn">
                <Icon name="ban" size={15} /> Chưa có đơn giá lương cho: {spMiss.map((c, i) => <span key={c}>{i ? ", " : ""}<b>{c}</b></span>)} — số SP các mã này KHÔNG được tính tiền. <a href="#/luong-sp">Cài đơn giá →</a>
              </div>
            )}
            {gioMiss.length > 0 && (
              <div class="wg-warn">
                <Icon name="ban" size={15} /> Thợ có GIỜ LÀM nhưng chưa đặt tiền 1 giờ: {gioMiss.map((n, i) => (
                  <span key={n}>{i ? ", " : ""}<a href={`#/sx-tho/${encodeURIComponent(n)}`}><b>{n}</b></a></span>
                ))} — đặt ở trang chi tiết thợ.
              </div>
            )}
          </>
        );
      })()}

      <section class="rs-sec">
        <div class="rs-sec-h"><Icon name="users" size={15} /> Theo thợ</div>
        {rep.workers.length === 0 ? (
          <EmptyState icon="✅">Không có báo cáo thợ nào trong khoảng này.</EmptyState>
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
                      {(w.days || []).length > 0 ? (
                        w.days!.map((d) => (
                          <div class="rs-wk-day" key={d.ymd}>
                            <div class="rs-wk-day-h">
                              <span class="rs-wk-day-date">📅 {d.ymd ? dm(d.ymd) : "?"}</span>
                              <span class="rs-wk-day-cay muted small">{soVN(d.cay)} SP</span>
                              <b class="rs-wk-day-money">{money(d.money)}</b>
                            </div>
                            {d.items.map((it, i) => (
                              <div class="wg-item" key={i}>
                                {(it.start || it.end) && (
                                  <span class="rs-item-time muted small">{it.start ? hhmm(it.start) : "?"}–{it.end ? hhmm(it.end) : "?"}</span>
                                )}
                                <span class="wg-item-code">{it.code || "?"}</span>
                                <span class="wg-item-calc muted small">{((it as any).gio || 0) > 0
                                  ? <>{soVN((it as any).gio)} giờ × {soVN((it as any).hourly_rate || 0)}đ</>
                                  : <>{soVN(it.cay)} SP × {soVN(it.wage)}đ</>}</span>
                                <span class="wg-item-money">{money(it.money)}</span>
                              </div>
                            ))}
                          </div>
                        ))
                      ) : (
                        w.items.map((it, i) => (
                          <div class="wg-item" key={i}>
                            <span class="wg-item-code">{it.code || "?"}</span>
                            <span class="wg-item-calc muted small">{((it as any).gio || 0) > 0
                              ? <>{soVN((it as any).gio)} giờ × {soVN((it as any).hourly_rate || 0)}đ</>
                              : <>{soVN(it.cay)} SP × {soVN(it.wage)}đ</>}</span>
                            <span class="wg-item-money">{money(it.money)}</span>
                          </div>
                        ))
                      )}
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
          <EmptyState icon="✅">Không có phiếu SX nào trong khoảng này.</EmptyState>
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
