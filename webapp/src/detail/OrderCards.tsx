// Card đơn hàng DÙNG CHUNG cho dashboard Đơn (OrdersList) + trang Khách
// (CustomerFeed): 3 kiểu xem full (CardBody+InvoiceMini) / compact (CompactBody)
// / ultra (UltraBody), badge 5 bước, nhóm theo ngày, tô sáng từ khoá.
// TÁCH TỪ OrdersList 2026-07-08 — sửa ở đây là ăn cả 2 trang.
import { useLayoutEffect, useRef, useState } from "preact/hooks";
import { fmtDateTimeVN, fmtRelative, fmtNgayGiao, foldVN } from "../format";
import { orderImageUrl } from "../api";
import { InvoiceTable } from "./InvoiceTable";
import { Icon } from "../ui/Icon";

export const NEW_ORDER_SEC = 5 * 60; // đơn tạo trong 5 phút → tô vàng + tag "Mới"

export type OrderRow = {
  thread_id: number;
  thumb_image_id?: number | null;
  thumb_image_ids?: number[];
  image_count?: number;
  customer: string;
  total: string;
  paid: number;
  remaining: number;
  date: string;
  hd_code: string;
  soan: boolean;
  giao: boolean;
  nop: boolean;
  nhan: boolean;
  done_after_20250124: boolean;
  invoice_count: number;
  invoice_summary?: { sp: string; sl: number | string }[];
  invoice_items?: { sp: string; sl: number | string; price: number }[];
  vat?: number;
  pvc?: number;
  discount?: number;
  no_truoc?: string;
  kh_debt?: number | null;
  created?: string;
  ngay_giao?: string;
  giao_by?: string;
  nop_by?: string;
  nop_note?: string;
  task_icons?: string;
  topic_name: string;
  creator: string;
  text: string;
  last_action?: string | null; // view 'Mới cập nhật': thao tác mới nhất (giàu như Lịch sử)
  last_detail?: string | null;
  last_changes?: { label: string; old: string; new: string }[];
  last_actor?: string | null;
  last_action_ts?: string | null;
  soan_img_ids?: number[];   // ảnh chốt soạn hàng — ưu tiên làm thumbnail
  nop_img_id?: number | null;
  task_bys?: string[];   // tên người HOÀN THÀNH từng bước (badge hiện tên thay nhãn)
};

// Mã ghi chú nộp tiền → tiếng Việt đầy đủ
const NOP_NOTE_VI: Record<string, string> = {
  co_ky_toa: "có ký toa",
  khong_ky_toa: "không ký toa",
  tra_tien_mat: "trả tiền mặt",
  chieu_lay_tien: "chiều lấy tiền",
};
const noteVi = (n?: string) => NOP_NOTE_VI[(n || "").toLowerCase()] || (n || "").replace(/_/g, " ").trim();

// Nhãn trạng thái workflow (thay cho "thiếu <số tiền>")
export function statusLabel(o: OrderRow): string {
  if (!o.soan) return "Chưa soạn";
  if (!o.giao) return "Chưa giao";
  if (!o.nop) {
    // "chiều lấy tiền": đã giao, hẹn thu sau (chưa nộp) → hiện rõ lý do
    if ((o.nop_note || "").toLowerCase() === "chieu_lay_tien") {
      const who = o.nop_by || o.giao_by;
      return `${who ? `${who} ` : ""}chiều lấy tiền`;
    }
    return o.giao_by ? `${o.giao_by} chưa nộp` : "Chưa nộp";
  }
  const note = noteVi(o.nop_note);
  return `${o.nop_by ? `${o.nop_by} ` : ""}đã nộp${note ? ` (${note})` : ""}`;
}

// Tô sáng KHÔNG DẤU. Tìm kiếm là LIKE %q% trên các trường ghép lại (tên KH + nội
// dung + mã SP), nên tách q theo khoảng trắng và tô SÁNG TỪNG TỪ ở mọi vị trí → khớp
// chéo trường ("Duy 5m") vẫn sáng đủ. foldVN giữ nguyên độ dài để map vị trí.
export function Highlight({ text, q }: { text: string; q: string }) {
  const s = text || "";
  const tokens = (q || "").trim().split(/\s+/).map(foldVN).filter((t) => t.length >= 1);
  if (!tokens.length || !s) return <>{s}</>;
  const fs = foldVN(s);
  const ranges: [number, number][] = [];
  for (const t of tokens) {
    let from = 0, idx: number;
    while ((idx = fs.indexOf(t, from)) !== -1) { ranges.push([idx, idx + t.length]); from = idx + t.length; }
  }
  if (!ranges.length) return <>{s}</>;
  ranges.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
    else merged.push([r[0], r[1]]);
  }
  const parts: any[] = [];
  let pos = 0, key = 0;
  for (const [a, b] of merged) {
    if (a > pos) parts.push(s.slice(pos, a));
    parts.push(<mark key={key++}>{s.slice(a, b)}</mark>);
    pos = b;
  }
  if (pos < s.length) parts.push(s.slice(pos));
  return <>{parts}</>;
}

// Bảng chi tiết hoá đơn 1 đơn (dùng ở card dashboard) — dùng chung InvoiceTable
export function InvoiceMini({ o, q }: { o: OrderRow; q?: string }) {
  if (!(o.invoice_items || []).length) return null;
  return <InvoiceTable items={o.invoice_items || []} discount={o.discount} pvc={o.pvc} vat={o.vat} debt={o.kh_debt} total={o.total} q={q} />;
}

// 5 task icon y hệt main message Telegram: HĐ · Soạn · Giao · Nộp · Nhận
const TASK_LABELS = ["HĐ", "Soạn", "Giao", "Nộp", "Nhận"];
// Dòng "thao tác mới nhất" trên card (view Mới cập nhật) — giàu như Lịch sử thao tác
export function LastAction({ o }: { o: OrderRow }) {
  if (!o.last_action) return null;
  const ch = Array.isArray(o.last_changes) ? o.last_changes : [];
  return (
    <div class="last-act">
      <div class="la-head"><Icon name="zap" size={13} /> <b>{o.last_action}</b>{o.last_detail ? <span> — {o.last_detail}</span> : null}</div>
      {ch.length > 0 && (
        <ul class="la-changes">
          {ch.slice(0, 4).map((c, ci) => (
            <li key={ci}>
              <span class="hc-label">{c.label}:</span>{" "}
              {c.old ? <span class="hc-old">{c.old}</span> : null}
              {c.old && c.new ? <span class="hc-arrow"> → </span> : null}
              {c.new ? <span class="hc-new">{c.new}</span> : null}
            </li>
          ))}
          {ch.length > 4 && <li class="muted">+{ch.length - 4} thay đổi nữa</li>}
        </ul>
      )}
      <div class="la-meta">{o.last_actor || "?"} · {fmtRelative(o.last_action_ts)}</div>
    </div>
  );
}

const _WD = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

/** Khoá ngày DD/MM/YYYY từ chuỗi giờ (dùng nhóm theo ngày). "?" nếu không parse được. */
export function dayKeyOf(created?: string): string {
  const mm = fmtDateTimeVN(created).match(/(\d{2})\/(\d{2})\/(\d{4})/);
  return mm ? `${mm[1]}/${mm[2]}/${mm[3]}` : "?";
}

/** Nhóm đơn theo NGÀY của trường đang SORT (giữ thứ tự hiện có; gộp liên tiếp cùng
 *  ngày): created (mặc định) | ngay_giao (chưa hẹn → nhóm "Chưa hẹn giao") | updated. */
export function groupOrdersByDay(orders: OrderRow[], by: "created" | "ngay_giao" | "updated" = "created"): { key: string; label: string; orders: OrderRow[] }[] {
  const out: { key: string; label: string; orders: OrderRow[] }[] = [];
  for (const o of orders) {
    let key: string, label: string | null = null;
    if (by === "ngay_giao") {
      // ngay_giao là ISO 'YYYY-MM-DD(THH:MM)' → lấy thẳng, khỏi vòng qua Date (lệch múi giờ)
      const m = (o.ngay_giao || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
      if (m) key = `${m[3]}/${m[2]}/${m[1]}`;
      else { key = "none"; label = "Chưa hẹn giao"; }
    } else if (by === "updated") {
      key = dayKeyOf(o.updated_at as any);
    } else {
      key = dayKeyOf(o.created);
    }
    const last = out[out.length - 1];
    if (last && last.key === key) last.orders.push(o);
    else out.push({ key, label: label ?? orderDayLabel(key), orders: [o] });
  }
  return out;
}

export function orderDayLabel(key: string): string {
  const [d, m, y] = key.split("/").map(Number);
  if (!d || !m || !y) return "Không rõ ngày";
  const date = new Date(y, m - 1, d);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const diff = Math.round((today.getTime() - date.getTime()) / 86400000);
  const wd = _WD[date.getDay()];
  const dm = key.slice(0, 5); // DD/MM
  if (diff === 0) return `Hôm nay · ${wd} ${dm}`;
  if (diff === 1) return `Hôm qua · ${wd} ${dm}`;
  if (diff === -1) return `Ngày mai · ${wd} ${dm}`;
  return `${wd} · ${key}`;
}

// Siêu gọn: chỉ 5 icon trạng thái + nội dung đơn 1 dòng (bỏ hết xuống dòng)
export function UltraBody({ o, search }: { o: OrderRow; search: string }) {
  const text = (o.text || o.topic_name || `#${o.thread_id}`).replace(/\s+/g, " ").trim();
  return (
    <div class="ultra-row">
      <TaskBadges o={o} />
      <span class="ultra-text"><Highlight text={text} q={search} /></span>
    </div>
  );
}

// Thân card two-col: cột thumbnail (trái) + nội dung (phải). ĐO chiều cao nội dung
// thật (ResizeObserver) → nếu đủ cho 2 ô vuông (H ≥ 2×rộng-cột + gap) thì hiện 2 ảnh.
export function CardBody({ o, search, stt, isNew, openThumb, filterByCustomer }: {
  o: OrderRow; search: string; stt: string; isNew: boolean;
  openThumb: (e: Event, o: OrderRow, atId?: number) => void;
  filterByCustomer?: (e: Event, c: string) => void;   // không truyền → ẩn nút lọc theo khách
}) {
  const allIds = o.thumb_image_ids && o.thumb_image_ids.length ? o.thumb_image_ids : (o.thumb_image_id ? [o.thumb_image_id] : []);
  const total = o.image_count ?? allIds.length;
  const contentRef = useRef<HTMLDivElement>(null);
  const colRef = useRef<HTMLDivElement>(null);
  const [two, setTwo] = useState(false);
  useLayoutEffect(() => {
    if (allIds.length < 2) { setTwo(false); return; }
    const el = contentRef.current;
    if (!el) return;
    const measure = () => {
      const h = el.offsetHeight; // chiều cao nội dung TỰ NHIÊN (không bị flex kéo giãn)
      const w = colRef.current?.offsetWidth || 100;
      setTwo(h >= 2 * w + 6); // 2 ô vuông xếp dọc + gap 6px
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    if (colRef.current) ro.observe(colRef.current);
    return () => ro.disconnect();
  }, [allIds.length, o.text, o.last_action, o.last_changes?.length, o.customer, o.total]);
  const shown = two ? allIds.slice(0, 2) : allIds.slice(0, 1);
  return (
    <div class="card-body">
      {allIds.length > 0 && (
        <div class="card-thumb-col" ref={colRef}>
          {shown.map((id, i) => (
            <span class="card-thumb-wrap" key={id} onClick={(e) => openThumb(e, o, id)}>
              <img class="card-thumb card-thumb-tile" src={orderImageUrl(o.thread_id, id, "thumb")} loading="lazy" alt="" />
              {i === shown.length - 1 && total > shown.length && <span class="thumb-count">+{total - shown.length}</span>}
            </span>
          ))}
        </div>
      )}
      <div class="card-content">
        <div class="cc-measure" ref={contentRef}>
          {o.text
            ? <div class="order-text wrap-badges"><TaskBadges o={o} />{o.ngay_giao && <span class="od-deliver"><Icon name="truck" size={14} /> {fmtNgayGiao(o.ngay_giao)}</span>}<span class="ot-text"><Highlight text={o.text} q={search} /></span></div>
            : <div class="order-text muted wrap-badges"><TaskBadges o={o} />{o.ngay_giao && <span class="od-deliver"><Icon name="truck" size={14} /> {fmtNgayGiao(o.ngay_giao)}</span>}<span class="ot-text">(không có nội dung)</span></div>}
          <div class="row space">
            <b class="cust">{isNew && <span class="tag-new">Mới</span>} <Highlight text={o.customer || o.topic_name || `#${o.thread_id}`} q={search} />
              {o.customer && filterByCustomer ? <button class="cust-filter" title={`Lọc đơn của ${o.customer}`} onClick={(e) => filterByCustomer(e, o.customer)}><Icon name="search" size={14} /></button> : null}</b>
            <span class="muted small order-when">
              {o.created ? <><Icon name="clock" size={13} /> {fmtDateTimeVN(o.created)} · {fmtRelative(o.created)}</> : o.date}
            </span>
          </div>
          <div class="row space">
            <span>
              {o.total && <b class="money">{o.total}</b>}
              {stt && <span class={stt.includes("đã nộp") ? "paid-ok" : "owe"}> · {stt}</span>}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// Thân card COMPACT: cột thumbnail (trái) + nội dung (phải). Đo chiều cao nội dung
// thật → đủ cho 2 ô vuông thì hiện 2 (giống card two-col, tile hẹp hơn ~68px).
export function CompactBody({ o, search, sort, flashMsg, isNew, openThumb }: {
  o: OrderRow; search: string; sort: string; flashMsg?: string; isNew: boolean;
  openThumb: (e: Event, o: OrderRow, atId?: number) => void;
}) {
  const allIds = o.thumb_image_ids && o.thumb_image_ids.length ? o.thumb_image_ids : (o.thumb_image_id ? [o.thumb_image_id] : []);
  const total = o.image_count ?? allIds.length;
  const contentRef = useRef<HTMLDivElement>(null);
  const colRef = useRef<HTMLDivElement>(null);
  const [two, setTwo] = useState(false);
  useLayoutEffect(() => {
    if (allIds.length < 2) { setTwo(false); return; }
    const el = contentRef.current;
    if (!el) return;
    const measure = () => {
      const w = colRef.current?.offsetWidth || 68;
      setTwo(el.offsetHeight >= 2 * w + 4);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    if (colRef.current) ro.observe(colRef.current);
    return () => ro.disconnect();
  }, [allIds.length, o.text, o.last_action, o.last_changes?.length, sort, flashMsg]);
  const shown = two ? allIds.slice(0, 2) : allIds.slice(0, 1);
  return (
    <>
      {allIds.length > 0 && (
        <div class="compact-thumb-col" ref={colRef}>
          {shown.map((id, i) => (
            <span class="card-thumb-wrap" key={id} onClick={(e) => openThumb(e, o, id)}>
              <img class="card-thumb card-thumb-tile" src={orderImageUrl(o.thread_id, id, "thumb")} loading="lazy" alt="" />
              {i === shown.length - 1 && total > shown.length && <span class="thumb-count">+{total - shown.length}</span>}
            </span>
          ))}
        </div>
      )}
      <div class="compact-right">
        <div class="cc-measure" ref={contentRef}>
          {sort === "updated" && <LastAction o={o} />}
          {flashMsg && <div class="flash-msg">🔔 {flashMsg}</div>}
          <div class="order-text wrap-badges">
            <TaskBadges o={o} />
            {o.ngay_giao && <span class="od-deliver"><Icon name="truck" size={14} /> {fmtNgayGiao(o.ngay_giao)}</span>}
            <span class="ot-text">
              {isNew && <span class="tag-new">Mới</span>}
              {o.text ? <Highlight text={o.text} q={search} /> : <span class="muted">(không có nội dung)</span>}
            </span>
          </div>
          <div class="order-when muted small">
            <Icon name="clock" size={13} /> {o.created ? <>{fmtDateTimeVN(o.created)} · {fmtRelative(o.created)}</> : o.date}
          </div>
        </div>
      </div>
    </>
  );
}

export function TaskBadges({ o }: { o: OrderRow }) {
  const icons = [...(o.task_icons || "")];
  const fallback: boolean[] = [false, o.soan, o.giao, o.nop, o.nhan];
  return (
    <span class="badges">
      {TASK_LABELS.map((label, i) => {
        // bước ĐÃ XONG → hiện TÊN người làm (thay nhãn); chưa xong → nhãn bước như cũ
        const by = (o.task_bys || [])[i];
        return (
          <span class="tstat" key={label}>
            <span class="tico">{icons[i] || (fallback[i] ? "✅" : "❌")}</span>
            <span class={"tlbl" + (by ? " tby" : "")}>{by || label}</span>
          </span>
        );
      })}
      {icons[5] && (
        <span class="tstat" key="no">
          <span class="tico">{icons[5]}</span>
          <span class="tlbl">{icons[5] === "😡" ? "Nợ" : "Tiền"}</span>
        </span>
      )}
    </span>
  );
}
