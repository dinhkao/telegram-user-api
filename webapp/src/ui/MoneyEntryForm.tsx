// Ô NHẬP TIỀN dùng chung (phụ cấp / ứng lương / các khoản tiền khác).
// Vì sao có file này: trước đây mỗi chỗ tự ghép <input class="pw-input"> rộng 82px —
// trên điện thoại gõ tiền triệu vào ô bằng đốt ngón tay, không đọc lại được số vừa gõ,
// dễ sai 1 số 0 (mà đây là tiền lương). Ở đây ô tiền là NHÂN VẬT CHÍNH:
//   - ô to hết chiều ngang, chữ lớn, có dấu chấm nghìn NGAY KHI GÕ + hậu tố "đ",
//   - dòng ĐỌC LẠI bằng chữ ("1 triệu 500 nghìn") để bắt lỗi thừa/thiếu số 0,
//   - chip cộng nhanh +10k…+1tr (bấm là CỘNG DỒN) + nút xoá,
//   - ngày (tuỳ chọn) kèm nút Hôm nay, ghi chú + chip gợi ý nội dung,
//   - nút lưu to, in luôn số tiền sắp ghi để xác nhận lần cuối.
// Controlled: cha giữ state (chuỗi CHỈ CHỮ SỐ cho tiền) → cha tự reset sau khi lưu.
// Dùng ở: detail/EntryPanel.tsx (popup ô bảng lương + view Thẻ), pages/AllowanceEntry,
// pages/AdvanceEntry — 3 chỗ cùng 1 hình dạng (luật ĐỒNG BỘ ở EntryPanel).
// Logic thuần (tách chữ số + đọc số bằng chữ) nằm ở format.ts để unit-test được —
// file .tsx có JSX nên node --test không nạp trực tiếp. Tests: tests/money.test.ts.
import { digitsOnly, docTien, moneyR as money } from "../format";
import { useState } from "preact/hooks";

/** Gốc để tính phụ cấp theo % (lương của THÁNG ĐANG XEM). value = số tiền làm gốc,
 *  label = nói rõ gốc là gì để người nhập không đoán mò. */
export type PctBase = { label: string; value: number };
/** Số % đã gõ (chuỗi, cho phép "12,5"). Trả về NaN nếu chưa gõ gì. */
const pctNum = (s: string) => {
  const t = String(s || "").replace(",", ".").replace(/[^\d.]/g, "");
  return t === "" ? NaN : Number(t);
};

const QUICK = [10_000, 50_000, 100_000, 500_000, 1_000_000];
const quickLabel = (v: number) => (v >= 1_000_000 ? `${v / 1_000_000} tr` : `${v / 1000}k`);
const todayISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export function MoneyEntryForm({
  amount, onAmount, note, onNote, date, onDate,
  amountLabel = "Số tiền", notePlaceholder = "Ghi chú", noteLabel = "Ghi chú",
  noteSuggestions, submitLabel = "Thêm", onSubmit, busy, before, compact,
  pctBase, onPct,
}: {
  amount: string;                       // CHUỖI CHỈ CHỮ SỐ (cha giữ)
  onAmount: (digits: string) => void;
  note: string; onNote: (v: string) => void;
  date?: string; onDate?: (v: string) => void;   // có onDate = hiện ô ngày
  amountLabel?: string; noteLabel?: string; notePlaceholder?: string;
  noteSuggestions?: string[];           // chip điền nhanh nội dung
  submitLabel?: string;
  onSubmit: () => void;
  busy?: boolean;
  before?: any;                         // slot trên ô tiền (vd: chọn thợ)
  compact?: boolean;                    // bản gọn cho popup/thẻ
  pctBase?: PctBase | null;             // có = hiện thêm kiểu nhập THEO %
  onPct?: (p: { pct: number; base: number } | null) => void;   // báo cha để ghi vào ghi chú
}) {
  const n = Number(amount || 0);
  const bump = (v: number) => onAmount(String(n + v));
  const submit = () => { if (!busy) onSubmit(); };
  // Kiểu nhập: tiền thẳng hay % của lương tháng. % chỉ là CÁCH TÍNH RA SỐ TIỀN —
  // thứ lưu xuống DB vẫn là số tiền chốt (khoản đã ghi bất biến), nên lương tháng
  // sau có đổi cũng không làm số phụ cấp đã ghi nhảy theo.
  const [mode, setMode] = useState<"vnd" | "pct">("vnd");
  const [pct, setPct] = useState("");
  const base = pctBase?.value || 0;
  const setPctAmt = (raw: string) => {
    setPct(raw);
    const v = pctNum(raw);
    if (!isFinite(v) || v <= 0 || base <= 0) { onAmount(""); onPct?.(null); return; }
    onAmount(String(Math.round((base * v) / 100)));
    onPct?.({ pct: v, base });
  };
  const toVnd = () => { setMode("vnd"); setPct(""); onPct?.(null); };

  return (
    <div class={compact ? "me-form compact" : "me-form"}>
      {before}
      {pctBase ? (
        <div class="seg me-modeseg" role="group" aria-label="Kiểu nhập">
          <button class={mode === "vnd" ? "seg-btn active" : "seg-btn"} type="button" onClick={toVnd}>Số tiền</button>
          <button class={mode === "pct" ? "seg-btn active" : "seg-btn"} type="button"
            onClick={() => { setMode("pct"); onAmount(""); }}>% lương</button>
        </div>
      ) : null}
      {mode === "pct" && pctBase ? (
        <>
          <label class="me-label" for="me-pct">Phần trăm của {pctBase.label}</label>
          <div class="me-amt-wrap">
            <input id="me-pct" class="me-amt" inputMode="decimal" autocomplete="off" placeholder="0"
              value={pct} onInput={(e: any) => setPctAmt(e.target.value)}
              onKeyDown={(e: any) => { if (e.key === "Enter") { e.preventDefault(); submit(); } }} />
            <span class="me-cur" aria-hidden="true">%</span>
            {pct ? <button class="me-clear" type="button" onClick={() => setPctAmt("")}
              aria-label="Xoá">✕</button> : null}
          </div>
          {/* nói rõ NHÂN VỚI SỐ NÀO ra SỐ NÀO — người duyệt lương phải kiểm được */}
          <div class={n > 0 ? "me-read" : "me-read empty"}>
            {base <= 0 ? `Tháng này ${pctBase.label} = 0đ nên chưa tính được`
              : n > 0 ? `${pct}% × ${money(base)}đ = ${money(n)}đ`
              : `gốc ${pctBase.label} ${money(base)}đ`}
          </div>
          <div class="me-quick">
            {[5, 10, 15, 20].map((v) => (
              <button class="chip me-chip" type="button" key={v} onClick={() => setPctAmt(String(v))}>{v}%</button>
            ))}
          </div>
        </>
      ) : (
        <>
          <label class="me-label" for="me-amt">{amountLabel}</label>
          <div class="me-amt-wrap">
            <input id="me-amt" class="me-amt" inputMode="numeric" autocomplete="off"
              placeholder="0" value={n ? money(n) : ""}
              onInput={(e: any) => onAmount(digitsOnly(e.target.value))}
              onKeyDown={(e: any) => { if (e.key === "Enter") { e.preventDefault(); submit(); } }} />
            <span class="me-cur" aria-hidden="true">đ</span>
            {n > 0 ? (
              <button class="me-clear" type="button" onClick={() => onAmount("")}
                aria-label="Xoá số tiền" title="Xoá số tiền">✕</button>
            ) : null}
          </div>
          {/* Đọc lại bằng chữ — chỗ duy nhất bắt được lỗi thừa/thiếu số 0 trước khi lưu */}
          <div class={n > 0 ? "me-read" : "me-read empty"}>{n > 0 ? docTien(n) : "chưa nhập số tiền"}</div>

          <div class="me-quick">
            {QUICK.map((v) => (
              <button class="chip me-chip" type="button" key={v} onClick={() => bump(v)}>+{quickLabel(v)}</button>
            ))}
          </div>
        </>
      )}

      {onDate ? (
        <>
          <label class="me-label" for="me-date">Ngày</label>
          <div class="me-daterow">
            <input id="me-date" class="me-date" type="date" value={date || ""}
              onInput={(e: any) => onDate(e.target.value)} />
            <button class="chip me-chip" type="button" onClick={() => onDate(todayISO())}>Hôm nay</button>
          </div>
        </>
      ) : null}

      <label class="me-label" for="me-note">{noteLabel}</label>
      <input id="me-note" class="me-note" placeholder={notePlaceholder} value={note}
        onInput={(e: any) => onNote(e.target.value)}
        onKeyDown={(e: any) => { if (e.key === "Enter") { e.preventDefault(); submit(); } }} />
      {noteSuggestions?.length ? (
        <div class="me-quick">
          {noteSuggestions.map((s) => (
            <button class={note === s ? "chip me-chip active" : "chip me-chip"} type="button" key={s}
              onClick={() => onNote(note === s ? "" : s)}>{s}</button>
          ))}
        </div>
      ) : null}

      <button class="btn primary block me-submit" type="button" disabled={busy || n <= 0} onClick={submit}>
        {busy ? "Đang ghi…" : n > 0 ? `${submitLabel} ${money(n)}đ` : submitLabel}
      </button>
    </div>
  );
}
