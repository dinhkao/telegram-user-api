// SỬA / NHẬP PHỤ CẤP 1 (phiếu, thợ) NGAY trong popup ô bảng lương SP theo ngày
// (detail/WagePivotCell) — văn phòng khỏi phải mở phiếu SX. Cùng API với khối tiền phiếu
// (POST /api/production/{tid}/allowance — ghi updated_by = người nhập ⇒ auto không đè).
// Gợi ý: số tiền viết trong ghi chú ("vít 15k") + bằng tiền người cao nhất/nhì phiếu
// (mốc quen thuộc của luật phụ cấp tự động). Lưu 0 ở ô đang ⚠ = "không phụ cấp" → tick
// "đã xử lý" (note-review/resolve) để ô hết đỏ. Lưu xong gọi onSaved để trang tải lại.
import { useEffect, useState } from "preact/hooks";
import { resolveNoteReview, setAllowance } from "../api";
import { digitsOnly, docTien, foldVN, moneyR as money } from "../format";
import { toast } from "../ui/feedback";

export type AllowSuggest = { label: string; amount: number };

/** Số tiền viết tay trong ghi chú — GƯƠNG gọn của allowance_auto.parse_note_amount. */
export function noteAmount(note: string): number | null {
  const f = foldVN(note || "").toLowerCase();
  let m = f.match(/\b(\d+(?:[.,]\d+)?)\s*(?:k|ng|nghin|ngan)\b/);
  if (m) return Math.round(Number(m[1].replace(",", ".")) * 1000);
  m = f.match(/\b(\d+)\s*(?:d|dong|vnd)\b/);
  if (m) return Number(m[1]);
  m = f.match(/\b(\d{1,3}(?:[.,]\d{3})+)\b/);
  return m ? Number(m[1].replace(/[.,]/g, "")) : null;
}

export function WagePivotAllowance({ threadId, worker, current, by, flag, suggest, onSaved }: {
  threadId: number; worker: string; current: number; by: string;
  flag?: { open: boolean; note: string } | null;
  suggest: AllowSuggest[]; onSaved: () => void;
}) {
  const [digits, setDigits] = useState(current ? String(Math.round(current)) : "");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setDigits(current ? String(Math.round(current)) : ""); }, [threadId, worker, current]);
  const n = Number(digits || 0);
  const unchanged = n === Math.round(current) && !(flag?.open && n === 0);

  const save = async () => {
    setBusy(true);
    try {
      await setAllowance(threadId, worker, n);
      // lưu 0 ở ô đang ⚠ = đã quyết "không phụ cấp" → tick đã xử lý cho ô hết đỏ
      if (n === 0 && flag?.open && flag.note) {
        await resolveNoteReview({ worker, note: flag.note, thread_id: threadId, worker_raw: worker });
      }
      toast(n ? `Đã lưu phụ cấp ${money(n)}đ cho ${worker}` : `Đã ghi: ${worker} không phụ cấp phiếu này`, "ok");
      onSaved();
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu phụ cấp", "err");
    } finally { setBusy(false); }
  };

  const src = !current ? "chưa có" : by === "auto" ? "tự động" : by ? `nhập tay · ${by}` : "";
  return (
    <div class={`wpa${flag?.open ? " need" : ""}`}>
      <div class="wpa-head">
        <b>Phụ cấp phiếu này</b>
        <span>{current ? `${money(current)}đ` : "0đ"}{src ? ` · ${src}` : ""}</span>
      </div>
      <label class="wpa-input">
        <input inputMode="numeric" placeholder="0" value={digits ? money(n) : ""}
          onInput={(e: any) => setDigits(digitsOnly(e.currentTarget.value).replace(/^0+/, ""))}
          onKeyDown={(e: any) => { if (e.key === "Enter" && !unchanged && !busy) save(); }} />
        <span>đ</span>
      </label>
      {n ? <div class="wpa-read">{docTien(n)}</div> : null}
      {suggest.length ? (
        <div class="wpa-chips">
          {suggest.map((s) => (
            <button type="button" key={s.label} class={`wpa-chip${s.amount === n ? " on" : ""}`}
              onClick={() => setDigits(s.amount ? String(s.amount) : "")}>
              <span>{s.label}</span><b>{s.amount ? money(s.amount) : "0"}</b>
            </button>
          ))}
        </div>
      ) : null}
      <button type="button" class="btn primary wpa-save" disabled={busy || unchanged} onClick={save}>
        {busy ? "Đang lưu…" : n ? `Lưu phụ cấp ${money(n)}đ` : flag?.open ? "Lưu: không phụ cấp (đã xem)" : "Bỏ phụ cấp"}
      </button>
    </div>
  );
}
