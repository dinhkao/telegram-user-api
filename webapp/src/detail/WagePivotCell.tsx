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
  let rows: { l: any; r: string; href?: string; zero?: boolean; note?: string }[] = [];
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
    // HIỆN CẢ PHIẾU 0đ: thợ có mặt trong ngày mà phiếu này không ra tiền cũng phải
    // thấy (biết là "đã tính rồi, bằng 0" chứ không phải "bị bỏ sót").
    const w = String(cell.wid);
    rows = cell.day.slips.map((s) => {
      const v = s.cells[w] || 0;
      const cay = s.cay?.[w] || 0;
      const pc = s.pc?.[w] || 0;
      const note = s.notes?.[w] || "";
      // số lượng/phụ cấp đi kèm mã SP; GHI CHÚ tách hẳn thành CỘT RIÊNG cho dễ đọc
      const bits: string[] = [];
      if (cay) bits.push(`${String(cay).replace(".", ",")} cây`);
      if (pc) bits.push(`phụ cấp ${money(pc)}đ`);
      return {
        l: (
          <span class="wpc-l">
            <b>{s.code || "—"}</b>
            {s.start ? <span class="muted small"> · {s.start}{s.end ? `–${s.end}` : ""}</span> : null}
            {bits.length ? <span class="muted small wpc-sub">{bits.join(" · ")}</span> : null}
          </span>
        ),
        note,
        r: `${money(v)}đ`,
        href: `#/san_xuat/${s.thread_id}`,
        zero: !v,
      };
    });
  } else {
    const { slip, wid } = cell;
    title = `${nameOf(wid)} · ${slip.code || "—"}`;
    sub = `phiếu #${slip.thread_id}${slip.start ? ` · ${slip.start}${slip.end ? `–${slip.end}` : ""}` : ""} · ${dmyOf(cell.day.ymd)}`;
    total = slip.cells[String(wid)] || 0;
    const parts = slip.parts?.[String(wid)] || [];
    const cay = slip.cay?.[String(wid)] || 0;
    if (cay) rows.push({ l: <span class="muted">Sản lượng</span>, r: `${String(cay).replace(".", ",")} cây` });
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
    const note = slip.notes?.[String(wid)] || "";
    if (note) rows.push({ l: <span class="muted">Ghi chú báo cáo: {note}</span>, r: "" });
    if (!rows.length) rows.push({ l: <span class="muted">không có dòng cấu thành</span>, r: `${money(total)}đ` });
  }

  return (
    <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="modal-sheet pr-pop-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head"><Icon name="wallet" size={18} /> {title}</div>
        <p class="muted small">{sub}</p>
        {rows.map((r, i) => (
          r.href
            ? <a class={`pr-pop-row wpc-row tappable${r.zero ? " wpc-zero" : ""}`} key={i} href={r.href} onClick={onClose}>
                <span>{r.l}</span>
                <span class="wpc-note">{r.note || ""}</span>
                <b>{r.r}</b>
              </a>
            : <div class="pr-pop-row" key={i}><span>{r.l}</span><b>{r.r}</b></div>
        ))}
        <div class="pr-pop-row hl"><span><b>Tổng ô này</b></span><b>{money(total)}đ</b></div>
        <button class="btn sh-cancel" onClick={onClose}>Đóng</button>
      </div>
    </div>
  );
}
