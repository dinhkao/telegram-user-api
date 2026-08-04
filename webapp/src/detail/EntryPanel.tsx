// PANEL KHOẢN TIỀN theo tháng (phụ cấp / ứng lương) — liệt kê + THÊM + VÔ HIỆU +
// SỬA GHI CHÚ. Dùng ở popup ô P.cấp/Ứng của bảng lương tháng (detail/PayrollCellPopup)
// và view Thẻ (detail/PayrollCard).
// Ô nhập = ui/MoneyEntryForm (ô tiền to, đọc lại bằng chữ, chip cộng nhanh) — trước
// đây là 3 input bé xíu nằm ngang, gõ tiền trên điện thoại rất dễ sai số 0.
// ⚠ ĐỒNG BỘ 2 CHỖ: panel này và 2 trang nhập (pages/AdvanceEntry.tsx +
// pages/AllowanceEntry.tsx) hiện CÙNG một khoản → thêm/sửa tính năng nào (nút, cột,
// thông tin dòng) phải làm ở CẢ HAI, đừng để 1 bên có 1 bên không.
// Dòng hiện: ngày (ứng) · tiền · badge VÔ HIỆU · ghi chú · ai tạo lúc nào · lý do vô hiệu.
import { useEffect, useRef, useState } from "preact/hooks";
import { Icon } from "../ui/Icon";
import { MoneyEntryForm, type DayBase, type PctBase } from "../ui/MoneyEntryForm";

/** Cách tính đã dùng để ra số tiền — ghi vào ghi chú khoản cho tra lại được. */
export type PctInfo = { kind: "pct" | "day"; n: number; base: number; label: string } | null;
import { toast } from "../ui/feedback";
import { moneyR as money, dmy, isoDate, tsLabel } from "../format";

/** Gợi ý nội dung hay dùng — bấm 1 phát khỏi gõ (bấm lại để bỏ chọn). */
export const PC_GOI_Y = ["Ăn trưa", "Xăng xe", "Chuyên cần", "Tăng ca"];
export const UNG_GOI_Y = ["Ứng tiêu", "Việc gia đình", "Ứng trước lương"];

export type MoneyEntry = {
  id: number; amount: number; note: string; adv_date?: string;
  created_by?: string; created_at?: string;
  voided_at?: string; voided_by?: string; void_reason?: string;
  calc_label?: string;                  // "10% lương gốc" — khoản tính theo công thức
};

export function EntryPanel({ entries, showDate, addPlaceholder, submitLabel, noteLabel,
  notePlaceholder, noteSuggestions, pctBase, dayBase, onAdd, onDel, onNote, extra }: {
  entries?: MoneyEntry[];
  showDate?: boolean;
  addPlaceholder: string;               // nhãn ô tiền ("Số tiền phụ cấp"…)
  submitLabel?: string;
  noteLabel?: string; notePlaceholder?: string; noteSuggestions?: string[];
  pctBase?: PctBase | null;             // có = cho nhập theo % lương tháng
  dayBase?: DayBase | null;             // có = cho nhập đơn giá × ngày công
  // calc = CÔNG THỨC đã dùng (nếu có) → chỗ gọi lưu xuống để tính lại sau này
  onAdd: (amount: number, note: string, date: string, calc?: { kind: "pct" | "day"; value: number } | null) => void;
  onDel: (id: number) => void;
  onNote?: (id: number, current: string) => void;   // ✏️ sửa ghi chú (tiền bất biến)
  extra?: any;
}) {
  const [amt, setAmt] = useState("");
  const [date, setDate] = useState(() => isoDate(new Date()));   // mặc định HÔM NAY
  const [note, setNote] = useState("");
  // Nhập theo % thì GHI LUÔN cách tính vào ghi chú (nếu người dùng chưa tự ghi) —
  // tháng sau nhìn lại phải biết 904.261đ ở đâu ra, vì DB chỉ lưu SỐ TIỀN chốt.
  const [pct, setPct] = useState<PctInfo>(null);
  // TÔ SÁNG dòng vừa ghi trong ~4s: danh sách có thể dài, thêm xong mà không chỉ rõ
  // "dòng này của bạn vừa nãy" thì người dùng không biết đã ăn hay chưa.
  const [fresh, setFresh] = useState<number[]>([]);
  const maxIdRef = useRef<number | null>(null);
  useEffect(() => {
    if (!entries) return;
    const max = entries.reduce((m, e) => Math.max(m, e.id), 0);
    if (maxIdRef.current === null) { maxIdRef.current = max; return; }   // lần nạp đầu
    if (max > maxIdRef.current) {
      const added = entries.filter((e) => e.id > (maxIdRef.current as number)).map((e) => e.id);
      maxIdRef.current = max;
      setFresh(added);
      const t = setTimeout(() => setFresh([]), 4000);
      return () => clearTimeout(t);
    }
    maxIdRef.current = max;
  }, [entries]);
  const add = () => {
    const a = Number(amt || 0);
    if (a <= 0) { toast("Nhập số tiền", "err"); return; }
    // có công thức thì KHÔNG nhét số gốc vào ghi chú nữa: gốc đổi là ghi chú sai
    const auto = note;
    onAdd(a, auto, date, pct ? { kind: pct.kind, value: pct.n } : null);
    setAmt(""); setNote(""); setPct(null);
  };
  return (
    <div class="pr-adv">
      {extra}
      {(entries || []).map((e) => (
        <div class={`pr-adv-row${e.voided_at ? " ua-voided" : ""}${fresh.includes(e.id) ? " just-added" : ""}`} key={e.id}>
          {/* 2 CỘT: tiền (+ngày) bên trái · ghi chú bên phải — trước đây ghi chú nằm
              DƯỚI số tiền nên nhiều khoản là một khối chữ dày, đọc rất mệt. */}
          <div class="ua-amt-col">
            {showDate ? <span class="muted small">{dmy(e.adv_date)}</span> : null}
            <b class={e.voided_at ? "ua-amt-voided" : ""}>{money(e.amount)}</b>
            {e.voided_at ? <span class="ua-void-badge">VÔ HIỆU</span> : null}
            {fresh.includes(e.id) ? <span class="ua-new-badge">VỪA THÊM</span> : null}
          </div>
          <div class="ua-note-col">
            {(e as any).calc_label ? <div class="ua-calc">{(e as any).calc_label}</div> : null}
            {e.note ? <div class="ua-note-txt">{e.note}</div>
              : !e.voided_at ? <div class="muted small ua-note-empty">chưa có ghi chú</div> : null}
            {tsLabel(e.created_at) ? (
              <div class="muted small ua-ts">tạo {tsLabel(e.created_at)}{e.created_by ? ` · ${e.created_by}` : ""}</div>
            ) : null}
            {e.voided_at ? (
              <div class="small ua-void-info">vô hiệu {tsLabel(e.voided_at)}{e.voided_by ? ` · ${e.voided_by}` : ""}{e.void_reason ? ` — ${e.void_reason}` : ""}</div>
            ) : null}
          </div>
          {!e.voided_at && onNote ? (
            <button class="ua-note-edit" onClick={() => onNote(e.id, e.note || "")} aria-label="Sửa ghi chú" title="Sửa ghi chú"><Icon name="edit" size={14} /></button>
          ) : null}
          {!e.voided_at ? <button class="pr-adv-del" onClick={() => onDel(e.id)} aria-label="Vô hiệu">✕</button> : null}
        </div>
      ))}
      {entries && !entries.length ? <div class="muted small">Chưa có khoản nào.</div> : null}
      <MoneyEntryForm compact amount={amt} onAmount={setAmt} note={note} onNote={setNote}
        date={showDate ? date : undefined} onDate={showDate ? setDate : undefined}
        amountLabel={addPlaceholder} submitLabel={submitLabel || "Thêm"}
        noteLabel={noteLabel || "Ghi chú"} notePlaceholder={notePlaceholder || "Ghi chú (tuỳ chọn)"}
        noteSuggestions={noteSuggestions} pctBase={pctBase} dayBase={dayBase}
        onPct={setPct} onSubmit={add} />
    </div>
  );
}
