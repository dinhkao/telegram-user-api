// POPUP THÊM KHOẢN (phụ cấp / ứng lương) — tách RIÊNG khỏi danh sách khoản.
// Vì sao tách: trước đây form nhập nằm ngay dưới danh sách trong cùng một popup, mà
// form giờ khá cao (3 kiểu nhập + chip + ngày + ghi chú) nên đẩy danh sách khoản
// trôi mất, nhìn rối. Giờ danh sách gọn lại, bấm "＋ Thêm…" mới mở form.
// Dùng bởi detail/EntryPanel (popup ô bảng lương + view Thẻ).
import { MoneyEntryForm, type DayBase, type PctBase } from "../ui/MoneyEntryForm";
import { Icon } from "../ui/Icon";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";

export function EntryAddPopup({ title, amount, onAmount, note, onNote, date, onDate,
  printNote, onPrintNote,
  amountLabel, submitLabel, noteLabel, notePlaceholder, noteSuggestions,
  pctBase, dayBase, onPct, onSubmit, onClose, extra }: {
  title: string;
  amount: string; onAmount: (v: string) => void;
  note: string; onNote: (v: string) => void;
  // chữ in trên phiếu lương (chỉ phụ cấp truyền vào — xem ui/MoneyEntryForm)
  printNote?: string; onPrintNote?: (v: string) => void;
  date?: string; onDate?: (v: string) => void;
  amountLabel: string; submitLabel: string;
  noteLabel?: string; notePlaceholder?: string; noteSuggestions?: string[];
  pctBase?: PctBase | null; dayBase?: DayBase | null;
  onPct?: (p: any) => void;
  onSubmit: () => void; onClose: () => void;
  extra?: any;   // khối phụ dưới form (VD: chép phụ cấp tháng trước — detail/PrevAllowances)
}) {
  usePopupBack(true, onClose);
  useScrollLock(true);
  return (
    <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="modal-sheet pr-pop-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head"><Icon name="plus" size={18} /> {title}</div>
        <MoneyEntryForm amount={amount} onAmount={onAmount} note={note} onNote={onNote}
          printNote={printNote} onPrintNote={onPrintNote}
          date={date} onDate={onDate} amountLabel={amountLabel} submitLabel={submitLabel}
          noteLabel={noteLabel} notePlaceholder={notePlaceholder} noteSuggestions={noteSuggestions}
          pctBase={pctBase} dayBase={dayBase} onPct={onPct} onSubmit={onSubmit} />
        {extra}
        <button class="btn sh-cancel" onClick={onClose}>Đóng</button>
      </div>
    </div>
  );
}
