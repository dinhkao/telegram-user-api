// POPUP CHI TIẾT 1 Ô của bảng pivot lương SP (#/luong-ngay) — bấm ô nào hiện đúng
// CẤU THÀNH của số tiền ô đó, để văn phòng kiểm được chứ không phải tin suông:
//   · ô PHIẾU (thợ × phiếu) → thanh SP/TC/PC, cách tính từng dòng (cây × đơn giá, tăng
//     ca, phụ cấp tự động hay nhập tay), giờ phiếu trên trục ngày, ghi chú, so với các
//     thợ khác CÙNG PHIẾU (mốc phụ cấp tự động lấy theo bảng này),
//   · ô NGÀY  (thợ × ngày)  → trục giờ các phiếu trong ngày + danh sách phiếu,
//   · ô TỔNG ngày           → chia cho những thợ nào + các phiếu trong ngày.
// Bấm 1 phiếu/1 thợ trong popup là ĐI SÂU (ngăn xếp, nút ‹ / nút BACK quay lại).
// Mỗi kiểu có dải link sang trang liên quan (phiếu SX, sửa báo cáo, SP, thợ, lương
// tháng, chấm công). Tính toán thuần: detail/wagePivotData.ts; khối hình:
// detail/WagePivotParts.tsx. Dữ liệu: production_store/wage_pivot.py.
import { useState } from "preact/hooks";
import type { ComponentChildren } from "preact";
import { type WagePivot, type WagePivotDay, type WagePivotSlip } from "../api";
import { moneyR as money } from "../format";
import { Icon } from "../ui/Icon";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";
import {
  FLAG_LABEL, dateLabel, dayComp, dayTotalComp, fmtDur, hm, isSunday, slipComp, slipMinutes, slipsOf,
  slipTotalComp, soVN,
} from "./wagePivotData";
import { CompBar, DayTimeline, LinkChips, RankBars, Section, type LinkItem } from "./WagePivotParts";
import { noteAmount, WagePivotAllowance, type AllowSuggest } from "./WagePivotAllowance";

export type PivotCell =
  | { kind: "day"; day: WagePivotDay; wid: number }
  | { kind: "slip"; day: WagePivotDay; slip: WagePivotSlip; wid: number }
  | { kind: "dayTotal"; day: WagePivotDay };

type View = { title: string; sub: string; total: number; body: ComponentChildren; links: LinkItem[] };

/** Mỗi tầng đi sâu giữ 1 mốc history → nút BACK của máy lùi đúng 1 tầng. */
function BackGuard({ onBack }: { onBack: () => void }) {
  usePopupBack(true, onBack);
  return null;
}

const span = (s: { start: string; end: string }) =>
  s.start || s.end ? `${hm(s.start) || "?"}–${hm(s.end) || "?"}` : "không ghi giờ";
const slipHasOt = (s: WagePivotSlip, wid?: number) =>
  Object.entries(s.parts || {}).some(([w, ps]) => (wid == null || w === String(wid)) && ps.some((p) => (p.ot || 0) > 0));

/** Khối cảnh báo đầu popup ô PHIẾU: ghi chú lệch câu chuẩn → auto không trả phụ cấp. */
function FlagBox({ kind, label, note, legacy }: { kind: "open" | "done"; label: string; note: string; legacy?: number }) {
  return (
    <div class={`wpc-flag ${kind}`} role="note">
      <b>⚠ {kind === "open" ? "Cần xem lại phụ cấp" : "Đã xử lý"}</b>
      <span>{label}: “{note}”. Phụ cấp tự động chỉ chạy khi ghi chú <b>trùng khít</b> câu chuẩn
        (vd “vít kẹo”, “quậy kẹo”) — ô này {kind === "open" ? "cần văn phòng tự quyết và nhập tay" : "văn phòng đã nhập tay / đã tick xử lý"}.</span>
      {legacy ? <span>Phụ cấp {money(legacy)}đ đang có là do quy tắc CŨ tự ghi (khớp lỏng theo từ khoá) — kiểm tra lại số này.</span> : null}
    </div>
  );
}

export function WagePivotCell({ cell, data, onClose, onChanged }: {
  cell: PivotCell; data: WagePivot; onClose: () => void;
  onChanged?: () => void;             // đã sửa phụ cấp → trang tải lại bảng
}) {
  usePopupBack(true, onClose);
  useScrollLock(true);
  const [stack, setStack] = useState<PivotCell[]>([cell]);
  // Tra lại ngày/phiếu trong `data` MỚI NHẤT: sửa phụ cấp xong trang tải lại bảng, ngăn
  // xếp vẫn giữ object cũ → phải map theo ymd/thread_id thì popup mới hiện số vừa lưu.
  const live = (c: PivotCell): PivotCell => {
    const day = data.days.find((d) => d.ymd === c.day.ymd) || c.day;
    if (c.kind !== "slip") return { ...c, day };
    return { ...c, day, slip: day.slips.find((x) => x.thread_id === c.slip.thread_id) || c.slip };
  };
  const cur = live(stack[stack.length - 1]);
  const push = (c: PivotCell) => setStack((s) => [...s, c]);
  const pop = () => setStack((s) => (s.length > 1 ? s.slice(0, -1) : s));

  const nameOf = (id: number) => data.workers.find((w) => w.id === id)?.name || `#${id}`;
  const ym = cur.day.ymd.slice(0, 7);
  const workerLinks = (wid: number): LinkItem[] => [
    { icon: "factory", label: "Sản xuất của thợ", href: `#/sx-tho/${encodeURIComponent(nameOf(wid))}` },
    { icon: "wallet", label: "Lương tháng", href: `#/luong-thang/${wid}?ym=${ym}` },
    { icon: "clock", label: "Chấm công", href: `#/cham-cong/${wid}?ym=${ym}` },
  ];
  const slipLinks = (s: WagePivotSlip): LinkItem[] => [
    { icon: "clipboard", label: `Phiếu SX #${s.thread_id}`, href: `#/san_xuat/${s.thread_id}` },
    { icon: "edit", label: "Sửa báo cáo", href: `#/san_xuat/${s.thread_id}/bao-cao` },
    ...(s.code ? [{ icon: "box", label: `Sản phẩm ${s.code}`, href: `#/kho/${encodeURIComponent(s.code)}` }] : []),
  ];

  const v: View = cur.kind === "slip" ? slipView(cur) : cur.kind === "day" ? dayView(cur) : totalView(cur);

  // ── ô PHIẾU: 1 thợ trong 1 phiếu ──────────────────────────────────────────────
  function slipView({ day, slip: s, wid }: { day: WagePivotDay; slip: WagePivotSlip; wid: number }): View {
    const w = String(wid);
    const c = slipComp(s, wid);
    const parts = s.parts?.[w] || [];
    const pcBy = s.pc_by?.[w] || "";
    const note = s.notes?.[w] || "";
    const mins = slipMinutes(s);
    const calc: { l: ComponentChildren; r: string; cls?: string }[] = [];
    for (const p of parts) {
      if (p.gio > 0) calc.push({ l: <>{soVN(p.gio)} giờ × {money(p.rate)}đ/giờ <span class="muted">(lương theo giờ)</span></>, r: money(Math.round(p.gio * p.rate)) });
      else if (p.cay > 0) calc.push({ l: <>{soVN(p.cay)} cây × {money(p.wage)}đ/cây{p.code && p.code !== s.code ? <span class="muted"> · {p.code}</span> : null}</>, r: money(Math.round(p.cay * p.wage)) });
      if (p.ot) calc.push({ l: <>Tăng ca {p.ot_min ? `${p.ot_min} phút` : ""} · +20% đơn giá<span class="wpc-why">{isSunday(day.ymd) ? "chủ nhật — cả phiếu là tăng ca" : "phần phiếu nằm sau 17:00"}</span></>, r: money(p.ot), cls: "tc" });
    }
    if (s.ot_off?.[w]) calc.push({ l: <>Tăng ca<span class="wpc-why">văn phòng đã TẮT tăng ca của thợ này ở phiếu này</span></>, r: "0", cls: "off" });
    if (c.pc) {
      const src = pcBy === "auto" ? "tự động theo ghi chú báo cáo" : pcBy ? `nhập tay · ${pcBy}` : "ghi trong phiếu";
      calc.push({ l: <>Phụ cấp<span class="wpc-why">{src}</span></>, r: money(c.pc), cls: "pc" });
    }
    // gợi ý số phụ cấp: số viết trong ghi chú + bằng tiền (SP + tăng ca) người cao nhất/nhì phiếu
    const sug: AllowSuggest[] = [];
    const fromNote = noteAmount(note);
    if (fromNote) sug.push({ label: "Theo ghi chú", amount: fromNote });
    const tops = data.workers
      .filter((x) => x.id !== wid)
      .map((x) => { const k = slipComp(s, x.id); return { name: x.name, v: k.sp + k.tc }; })
      .filter((x) => x.v > 0)
      .sort((a, b) => b.v - a.v);
    if (tops[0]) sug.push({ label: `Cao nhất · ${tops[0].name}`, amount: tops[0].v });
    if (tops[1]) sug.push({ label: `Cao nhì · ${tops[1].name}`, amount: tops[1].v });
    const fl = s.flag?.[w];
    const editor = (
      <WagePivotAllowance threadId={s.thread_id} worker={s.raw?.[w] || nameOf(wid)} current={c.pc} by={pcBy}
        flag={fl ? { open: !fl.done, note: fl.note || note } : null} suggest={sug}
        onSaved={() => onChanged?.()} />
    );
    const mine = slipsOf(day, wid);
    const peers = data.workers
      .map((x) => ({ key: x.id, name: x.name, value: s.cells[String(x.id)] || 0, active: x.id === wid,
        sub: s.cay?.[String(x.id)] ? `${soVN(s.cay[String(x.id)])} cây${s.pc?.[String(x.id)] ? " · có phụ cấp" : ""}` : undefined }))
      .filter((r) => r.value)
      .sort((a, b) => b.value - a.value);
    return {
      title: nameOf(wid),
      sub: `${s.code || "—"} · phiếu #${s.thread_id}${s.kind === "dong_goi" ? " · đóng gói" : ""} · ${dateLabel(day.ymd)}`,
      total: c.total,
      body: (
        <>
          {s.flag?.[w] ? <FlagBox kind={s.flag[w].done ? "done" : "open"} label={FLAG_LABEL[s.flag[w].kind] || "ghi chú lệch chuẩn"} note={note}
            legacy={!s.flag[w].done && pcBy === "auto" ? c.pc : 0} /> : null}
          {fl && !fl.done ? editor : null}
          <CompBar c={c} />
          <Section title="Cách tính">
            <div class="wpc-calc">
              {s.cay?.[w] ? <div class="wpc-calc-row muted"><span>Sản lượng</span><b>{soVN(s.cay[w])} cây</b></div> : null}
              {calc.map((r, i) => <div key={i} class={`wpc-calc-row ${r.cls || ""}`}><span>{r.l}</span><b>{r.r}đ</b></div>)}
              <div class="wpc-calc-row sum"><span>Tổng ô này</span><b>{money(c.total)}đ</b></div>
            </div>
          </Section>
          {fl && !fl.done ? null : editor}
          {note ? <Section title="Ghi chú báo cáo"><blockquote class="wpc-quote">{note}</blockquote></Section> : null}
          <Section title="Giờ làm trong ngày" right={<span class="muted small">{span(s)}{mins ? ` · ${fmtDur(mins)}` : ""}</span>}>
            <DayTimeline sunday={isSunday(day.ymd)}
              blocks={mine.map((x) => ({ key: x.thread_id, label: x.code || "—", start: x.start, end: x.end, active: x.thread_id === s.thread_id, ot: slipHasOt(x, wid) }))}
              onPick={(k) => { const t = mine.find((x) => x.thread_id === k); if (t && t !== s) push({ kind: "slip", day, slip: t, wid }); }} />
          </Section>
          {peers.length > 1 ? (
            <Section title={`Cả phiếu · ${peers.length} thợ`} right={<span class="muted small">{money(s.total)}đ</span>}>
              <RankBars rows={peers} onPick={(k) => { if (k !== wid) push({ kind: "slip", day, slip: s, wid: Number(k) }); }} />
            </Section>
          ) : null}
        </>
      ),
      links: [
        ...slipLinks(s),
        { icon: "calendar", label: `Cả ngày của ${nameOf(wid)}`, onClick: () => push({ kind: "day", day, wid }) },
        ...workerLinks(wid),
      ],
    };
  }

  // ── ô NGÀY: 1 thợ trong 1 ngày ─────────────────────────────────────────────────
  function dayView({ day, wid }: { day: WagePivotDay; wid: number }): View {
    const w = String(wid);
    const mine = slipsOf(day, wid);
    const c = dayComp(day, wid);
    const workMin = mine.reduce((a, s) => a + slipMinutes(s), 0);
    return {
      title: nameOf(wid),
      sub: `${dateLabel(day.ymd)} · ${mine.length} phiếu${workMin ? ` · ${fmtDur(workMin)}` : ""}`,
      total: day.cells[w] || 0,
      body: (
        <>
          <CompBar c={c} />
          <Section title="Giờ làm trong ngày">
            <DayTimeline sunday={isSunday(day.ymd)}
              blocks={mine.map((s) => ({ key: s.thread_id, label: s.code || "—", start: s.start, end: s.end, ot: slipHasOt(s, wid) }))}
              onPick={(k) => { const s = mine.find((x) => x.thread_id === k); if (s) push({ kind: "slip", day, slip: s, wid }); }} />
          </Section>
          <Section title="Các phiếu" right={<span class="muted small">bấm để xem cách tính</span>}>
            <div class="wpc-slips">
              {mine.map((s) => {
                const sc = slipComp(s, wid);
                return (
                  <button type="button" key={s.thread_id} class={`wpc-slip${sc.total ? "" : " zero"}`}
                    onClick={() => push({ kind: "slip", day, slip: s, wid })}>
                    <span class="wpc-slip-time">{span(s)}</span>
                    <span class="wpc-slip-main">
                      <b>{s.code || "—"}</b>
                      <span class="wpc-tags">
                        {s.cay?.[w] ? <span class="wpc-tag">{soVN(s.cay[w])} cây</span> : null}
                        {sc.tc ? <span class="wpc-tag tc">TC {money(sc.tc)}</span> : null}
                        {s.ot_off?.[w] ? <span class="wpc-tag off">TC tắt</span> : null}
                        {sc.pc ? <span class="wpc-tag pc">PC {money(sc.pc)}{s.pc_by?.[w] === "auto" ? " · tự động" : ""}</span> : null}
                        {s.flag?.[w] ? <span class={`wpc-tag flag${s.flag[w].done ? " done" : ""}`}>⚠ ghi chú lệch chuẩn{s.flag[w].done ? " · đã xử lý" : ""}</span> : null}
                      </span>
                      {s.notes?.[w] ? <span class="wpc-slip-note">{s.notes[w]}</span> : null}
                    </span>
                    <b class="wpc-slip-amt">{money(sc.total)}đ</b>
                    <Icon name="chevronRight" size={16} />
                  </button>
                );
              })}
            </div>
          </Section>
        </>
      ),
      links: [
        ...workerLinks(wid),
        { icon: "users", label: "Cả xưởng ngày này", onClick: () => push({ kind: "dayTotal", day }) },
      ],
    };
  }

  // ── ô TỔNG NGÀY: cả xưởng 1 ngày ──────────────────────────────────────────────
  function totalView({ day }: { day: WagePivotDay }): View {
    const rows = data.workers
      .map((x) => {
        const n = slipsOf(day, x.id).length;
        return { key: x.id, name: x.name, value: day.cells[String(x.id)] || 0, sub: `${n} phiếu` };
      })
      .filter((r) => r.value)
      .sort((a, b) => b.value - a.value);
    return {
      title: dateLabel(day.ymd),
      sub: `cả xưởng · ${rows.length} thợ · ${day.slips.length} phiếu`,
      total: day.total,
      body: (
        <>
          <CompBar c={dayTotalComp(day, data)} />
          <Section title="Các phiếu trong ngày">
            <DayTimeline sunday={isSunday(day.ymd)}
              blocks={day.slips.map((s) => ({ key: s.thread_id, label: s.code || "—", start: s.start, end: s.end, ot: slipHasOt(s) }))} />
            <div class="wpc-slips">
              {day.slips.map((s) => {
                const sc = slipTotalComp(s, data);
                return (
                  <a key={s.thread_id} class="wpc-slip" href={`#/san_xuat/${s.thread_id}`}>
                    <span class="wpc-slip-time">{span(s)}</span>
                    <span class="wpc-slip-main">
                      <b>{s.code || "—"}</b>
                      <span class="wpc-tags">
                        <span class="wpc-tag">{Object.keys(s.cells).length} thợ</span>
                        {sc.tc ? <span class="wpc-tag tc">TC {money(sc.tc)}</span> : null}
                        {sc.pc ? <span class="wpc-tag pc">PC {money(sc.pc)}</span> : null}
                      </span>
                    </span>
                    <b class="wpc-slip-amt">{money(s.total)}đ</b>
                    <Icon name="chevronRight" size={16} />
                  </a>
                );
              })}
            </div>
          </Section>
          <Section title="Chia theo thợ" right={<span class="muted small">bấm để xem ngày của thợ</span>}>
            <RankBars rows={rows} onPick={(k) => push({ kind: "day", day, wid: Number(k) })} />
          </Section>
        </>
      ),
      links: [],
    };
  }

  return (
    <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      {stack.slice(1).map((_, i) => <BackGuard key={i} onBack={pop} />)}
      <div class="modal-sheet pr-pop-sheet wpc-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="wpc-head">
          {stack.length > 1
            ? <button type="button" class="wpc-ico" onClick={pop} aria-label="Quay lại"><Icon name="back" size={18} /></button>
            : <span class="wpc-ico static"><Icon name="wallet" size={18} /></span>}
          <div class="wpc-title">
            <b>{v.title}</b>
            <span>{v.sub}</span>
          </div>
          <button type="button" class="wpc-ico" onClick={onClose} aria-label="Đóng"><Icon name="close" size={18} /></button>
        </div>
        <div class="wpc-total"><span>{money(v.total)}</span><small>đ</small></div>
        {v.body}
        {v.links.length ? <Section title="Mở nhanh"><LinkChips items={v.links} /></Section> : null}
      </div>
    </div>
  );
}
