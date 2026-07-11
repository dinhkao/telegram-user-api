// Dashboard BÁO CÁO sản xuất (#/bao-cao) — CHỈ văn phòng (tiền lương).
// Văn phòng tạo phiếu báo cáo (chọn ngày bắt đầu + kết thúc, ghi chú tuỳ chọn);
// danh sách hiện tổng SP + tổng tiền từng phiếu. Bấm phiếu → chi tiết #/bao-cao/:id.
// Data: listReportSlips/createReportSlip. Realtime report_slips_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { createReportSlip, isOffice, listReportSlips, soVN, type ReportSlip } from "../api";
import { onRealtime } from "../realtime";
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { toast } from "../ui/feedback";

const pad = (n: number) => String(n).padStart(2, "0");
const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const dmy = (ymd: string) => (ymd && ymd.length >= 10 ? `${ymd.slice(8, 10)}/${ymd.slice(5, 7)}/${ymd.slice(0, 4)}` : ymd);
const money = (n: number) => soVN(Math.round(n)) + "đ";

// Thứ Hai của tuần chứa `d`
function monday(d: Date): Date {
  const m = new Date(d);
  m.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return m;
}

export function ReportSlips() {
  const [slips, setSlips] = useState<ReportSlip[] | null>(null);
  const [err, setErr] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try { setSlips(await listReportSlips()); setErr(""); }
    catch (e: any) { setErr(e?.message || "Lỗi tải báo cáo"); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "report_slips_changed" || e.type === "resync") { clearTimeout(t); t = setTimeout(load, 400); }
    });
    return () => { off(); clearTimeout(t); };
  }, []);

  const preset = (which: "this" | "last") => {
    const now = new Date();
    const mon = monday(now);
    if (which === "this") { setFrom(iso(mon)); setTo(iso(now)); }
    else {
      const lastMon = new Date(mon); lastMon.setDate(mon.getDate() - 7);
      const lastSun = new Date(mon); lastSun.setDate(mon.getDate() - 1);
      setFrom(iso(lastMon)); setTo(iso(lastSun));
    }
  };

  const create = async () => {
    if (busy) return;
    if (!from || !to) { toast("Phải chọn ngày bắt đầu và ngày kết thúc", "err"); return; }
    if (from > to) { toast("Ngày bắt đầu phải trước ngày kết thúc", "err"); return; }
    setBusy(true);
    try {
      const slip = await createReportSlip(from, to, note);
      toast("Đã tạo phiếu báo cáo", "ok");
      setNote("");
      window.location.hash = `#/bao-cao/${slip.id}`;
    } catch (e: any) {
      toast(e?.message || "Lỗi tạo báo cáo", "err");
    } finally {
      setBusy(false);
    }
  };

  const head = (
    <div class="wg-head">
      <BackLink fallback="#/home" />
      <div>
        <div class="wg-title"><Icon name="receipt" size={18} /> Báo cáo sản xuất</div>
        <div class="muted small">phiếu báo cáo theo khoảng ngày — SP + tiền công thợ</div>
      </div>
    </div>
  );

  if (!isOffice()) return <div class="rs-page">{head}<EmptyState icon="lock">Chỉ văn phòng được xem báo cáo.</EmptyState></div>;
  if (err) return <div class="rs-page">{head}<ErrorState msg={err} onRetry={load} /></div>;

  return (
    <div class="rs-page">
      {head}

      <section class="card rs-create">
        <label class="card-label">➕ Tạo phiếu báo cáo</label>
        <div class="rs-dates">
          <label class="rs-date-f">
            <span class="muted small">Từ ngày</span>
            <input type="date" value={from} max={to || undefined} onChange={(e: any) => setFrom(e.currentTarget.value)} />
          </label>
          <label class="rs-date-f">
            <span class="muted small">Đến ngày</span>
            <input type="date" value={to} min={from || undefined} onChange={(e: any) => setTo(e.currentTarget.value)} />
          </label>
        </div>
        <div class="rs-presets">
          <button class="rs-preset" onClick={() => preset("this")}>Tuần này</button>
          <button class="rs-preset" onClick={() => preset("last")}>Tuần trước</button>
        </div>
        <input class="rs-note" type="text" placeholder="Ghi chú (tuỳ chọn)…" value={note}
          onInput={(e: any) => setNote(e.currentTarget.value)} />
        <button class="btn primary block rs-create-btn" disabled={busy || !from || !to} onClick={create}>
          {busy ? "Đang tạo…" : "Tạo báo cáo"}
        </button>
      </section>

      {slips === null ? (
        <Loading />
      ) : slips.length === 0 ? (
        <EmptyState icon="receipt">Chưa có phiếu báo cáo nào — chọn khoảng ngày ở trên để tạo.</EmptyState>
      ) : (
        slips.map((s) => (
          <a class="card rs-row" key={s.id} href={`#/bao-cao/${s.id}`}>
            <div class="rs-row-main">
              <div class="rs-row-range"><Icon name="calendar" size={15} /> {dmy(s.from_ymd)} → {dmy(s.to_ymd)}</div>
              {s.note ? <div class="muted small rs-row-note">{s.note}</div> : null}
              <div class="muted small">{s.worker_count || 0} thợ · {s.phieu_count || 0} phiếu SX{s.created_by ? ` · tạo bởi ${s.created_by}` : ""}</div>
            </div>
            <div class="rs-row-nums">
              <b class="rs-row-money">{money(s.totals?.money || 0)}</b>
              <span class="muted small">{soVN(s.totals?.cay || 0)} SP</span>
            </div>
          </a>
        ))
      )}
    </div>
  );
}
