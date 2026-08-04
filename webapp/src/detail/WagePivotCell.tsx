// POPUP CHI TIẾT 1 Ô của bảng pivot lương SP (#/luong-ngay) — bấm ô nào hiện đúng
// CẤU THÀNH của số tiền ô đó, để văn phòng kiểm được chứ không phải tin suông:
//   · ô NGÀY  (thợ × ngày)  → ngày đó thợ làm những PHIẾU nào, mỗi phiếu bao nhiêu,
//   · ô PHIẾU (thợ × phiếu) → cây × đơn giá (hoặc giờ × đơn giá giờ) + phụ cấp phiếu,
//   · ô TỔNG ngày           → ngày đó chia cho những THỢ nào.
// ⚠ Phụ cấp phiếu đã được compute_range_report GỘP vào tiền của dòng đầu, nên phần
// "phụ cấp / khác" = tiền ô − Σ(cây × đơn giá) chứ không có trường riêng.
import { type WagePivot, type WagePivotDay, type WagePivotSlip } from "../api";
import { moneyR as money } from "../format";
import { Icon } from "../ui/Icon";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";

export type PivotCell =
  | { kind: "day"; day: WagePivotDay; wid: number }
  | { kind: "slip"; day: WagePivotDay; slip: WagePivotSlip; wid: number }
  | { kind: "dayTotal"; day: WagePivotDay };

const soVN = (n: number) => String(Math.round(n * 10) / 10).replace(".", ",");
const dmyOf = (ymd: string) => `${ymd.slice(8, 10)}/${ymd.slice(5, 7)}/${ymd.slice(0, 4)}`;

export function WagePivotCell({ cell, data, onClose }: {
  cell: PivotCell; data: WagePivot; onClose: () => void;
}) {
  usePopupBack(true, onClose);
  useScrollLock(true);
  const nameOf = (id: number) => data.workers.find((w) => w.id === id)?.name || `#${id}`;

  let title = "";
  let sub = "";
  let rows: { l: any; r: string; href?: string }[] = [];
  let total = 0;

  if (cell.kind === "dayTotal") {
    title = `Ngày ${dmyOf(cell.day.ymd)}`;
    sub = "tiền công ngày này chia cho từng thợ";
    total = cell.day.total;
    rows = data.workers
      .map((w) => ({ w, v: cell.day.cells[String(w.id)] || 0 }))
      .filter((x) => x.v)
      .sort((a, b) => b.v - a.v)
      .map((x) => ({ l: x.w.name, r: `${money(x.v)}đ` }));
  } else if (cell.kind === "day") {
    title = `${nameOf(cell.wid)} · ${dmyOf(cell.day.ymd)}`;
    sub = "ngày này làm những phiếu nào";
    total = cell.day.cells[String(cell.wid)] || 0;
    rows = cell.day.slips
      .map((s) => ({ s, v: s.cells[String(cell.wid)] || 0 }))
      .filter((x) => x.v)
      .map((x) => ({
        l: <>{x.s.code || "—"}{x.s.start ? <span class="muted small"> · {x.s.start}{x.s.end ? `–${x.s.end}` : ""}</span> : null}</>,
        r: `${money(x.v)}đ`,
        href: `#/san_xuat/${x.s.thread_id}`,
      }));
  } else {
    const { slip, wid } = cell;
    title = `${nameOf(wid)} · ${slip.code || "—"}`;
    sub = `phiếu #${slip.thread_id}${slip.start ? ` · ${slip.start}${slip.end ? `–${slip.end}` : ""}` : ""} · ${dmyOf(cell.day.ymd)}`;
    total = slip.cells[String(wid)] || 0;
    const parts = slip.parts?.[String(wid)] || [];
    let counted = 0;
    for (const p of parts) {
      if (p.gio > 0) {
        const v = Math.round(p.gio * p.rate);
        counted += v;
        rows.push({ l: <>{soVN(p.gio)} giờ × {money(p.rate)}đ/giờ</>, r: `${money(v)}đ` });
      } else if (p.cay > 0) {
        const v = Math.round(p.cay * p.wage);
        counted += v;
        rows.push({ l: <>{soVN(p.cay)} cây × {money(p.wage)}đ/cây</>, r: `${money(v)}đ` });
      }
    }
    // phần dôi ra = phụ cấp ghi trong phiếu (đã gộp sẵn vào tiền) — nói rõ ra
    const rest = total - counted;
    if (Math.abs(rest) >= 1) {
      rows.push({ l: <span class="t-ok">Phụ cấp ghi trong phiếu</span>, r: `${money(rest)}đ` });
    }
    if (!rows.length) rows.push({ l: <span class="muted">không có dòng cấu thành</span>, r: `${money(total)}đ` });
  }

  return (
    <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="modal-sheet pr-pop-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head"><Icon name="wallet" size={18} /> {title}</div>
        <p class="muted small">{sub}</p>
        {rows.map((r, i) => (
          r.href
            ? <a class="pr-pop-row tappable" key={i} href={r.href} onClick={onClose}><span>{r.l}</span><b>{r.r}</b></a>
            : <div class="pr-pop-row" key={i}><span>{r.l}</span><b>{r.r}</b></div>
        ))}
        <div class="pr-pop-row hl"><span><b>Tổng ô này</b></span><b>{money(total)}đ</b></div>
        <button class="btn sh-cancel" onClick={onClose}>Đóng</button>
      </div>
    </div>
  );
}
