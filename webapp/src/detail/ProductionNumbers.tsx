// Nhập số lượng đã nhận cho phiếu SX + danh sách các lần nhập. POST .../number
// (queueable — an toàn khi mất mạng). Cần đã chọn SP trước. Server đồng bộ Google
// Sheet (best-effort). onChanged() để trang chi tiết tải lại tổng.
import { useState } from "preact/hooks";
import { addProductionNumber, soVN, type ProdSlip } from "../api";

export function ProductionNumbers({
  threadId,
  slip,
  onChanged,
}: {
  threadId: string;
  slip: ProdSlip;
  onChanged: () => void;
}) {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const numbers = slip.numbers || [];
  const hasSp = !!slip.sp_name;

  const add = async () => {
    const n = parseFloat(amount.replace(",", "."));
    if (!isFinite(n)) {
      setMsg("Số lượng không hợp lệ");
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const r = await addProductionNumber(threadId, n, note.trim());
      setAmount("");
      setNote("");
      if (r?._queued) setMsg("⏳ Đã lưu tạm (mất mạng), sẽ gửi lại");
      else onChanged();
    } catch (e: any) {
      setMsg(e?.message || "Lỗi nhập số lượng");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section class="card">
      <label class="card-label">Nhập số lượng nhận</label>
      {!hasSp && <div class="muted small">Chọn sản phẩm trước khi nhập.</div>}
      <div class="row">
        <input
          type="text"
          inputMode="decimal"
          value={amount}
          disabled={!hasSp}
          onInput={(e) => setAmount((e.target as HTMLInputElement).value)}
          placeholder="Số lượng"
        />
        <input
          type="text"
          value={note}
          disabled={!hasSp}
          onInput={(e) => setNote((e.target as HTMLInputElement).value)}
          placeholder="Ghi chú (tuỳ chọn)"
        />
        <button class="btn primary" disabled={!hasSp || busy} onClick={add}>
          {busy ? "…" : "＋"}
        </button>
      </div>
      {msg && <div class="muted small">{msg}</div>}

      {numbers.length > 0 && (
        <ul class="prod-numbers">
          {numbers
            .slice()
            .reverse()
            .map((it, i) => (
              <li key={i}>
                <span class="prod-num-amt">{soVN(it.amount)}</span>
                {it.note && <span class="prod-num-note">{it.note}</span>}
              </li>
            ))}
        </ul>
      )}
    </section>
  );
}
