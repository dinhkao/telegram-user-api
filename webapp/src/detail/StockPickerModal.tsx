// Popup chọn thùng để xuất cho đơn — liệt kê thùng khả dụng (in_stock, còn hiệu
// lực) kèm info (số cây, NSX, ghi chú). Chọn nhiều thùng, mỗi thùng có thể lấy 1
// phần (mặc định full thùng). Trả picks cho OrderStock gọi allocatePicks.
import { useEffect, useMemo, useState } from "preact/hooks";
import { inventoryDetail, soVN, type InvBox } from "../api";
import { useScrollLock } from "../useScrollLock";

function fmtDate(s?: string | null): string {
  if (!s) return "";
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : s;
}

export function StockPickerModal({
  productCode,
  need,
  got,
  onClose,
  onPick,
}: {
  productCode: string;
  need: number;
  got: number;
  onClose: () => void;
  onPick: (picks: { box_id: number; quantity: number }[]) => Promise<void>;
}) {
  useScrollLock(true);
  const [boxes, setBoxes] = useState<InvBox[] | null>(null);
  const [sel, setSel] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    inventoryDetail(productCode)
      .then((d) => setBoxes(d.boxes))
      .catch((e: any) => setErr(e?.message || "Lỗi tải kho"));
  }, [productCode]);

  const remaining = Math.max(need - got, 0);

  const toggle = (b: InvBox) =>
    setSel((s) => {
      const n = { ...s };
      if (b.id in n) delete n[b.id];
      else n[b.id] = String(b.quantity);
      return n;
    });
  const setQty = (id: number, v: string) => setSel((s) => ({ ...s, [id]: v }));

  const pickedSum = useMemo(
    () =>
      Object.values(sel).reduce((t, v) => {
        const n = parseFloat(String(v).replace(",", "."));
        return t + (isFinite(n) && n > 0 ? n : 0);
      }, 0),
    [sel]
  );

  const submit = async () => {
    const picks: { box_id: number; quantity: number }[] = [];
    for (const [id, v] of Object.entries(sel)) {
      const n = parseFloat(String(v).replace(",", "."));
      if (isFinite(n) && n > 0) picks.push({ box_id: Number(id), quantity: n });
    }
    if (!picks.length) {
      setErr("Chưa chọn thùng");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      await onPick(picks);
      onClose();
    } catch (e: any) {
      setErr(e?.message || "Lỗi xuất kho");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="modal-overlay" onClick={onClose}>
      <div class="modal-sheet" onClick={(e) => e.stopPropagation()}>
        <div class="modal-head">
          <b>Chọn thùng — {productCode}</b>
          <button class="link-btn" onClick={onClose}>
            ✕
          </button>
        </div>
        <div class="muted small">
          Cần {soVN(need)} · đã xuất {soVN(got)} · còn thiếu {soVN(remaining)}
        </div>

        {!boxes ? (
          <div class="muted">Đang tải…</div>
        ) : boxes.length === 0 ? (
          <div class="muted small">Kho hết thùng {productCode}.</div>
        ) : (
          <div class="stock-pick-list">
            {boxes.map((b) => {
              const checked = b.id in sel;
              return (
                <div class={checked ? "stock-pick-row on" : "stock-pick-row"} key={b.id}>
                  <label class="stock-pick-main">
                    <input type="checkbox" checked={checked} onChange={() => toggle(b)} />
                    <span class="stock-pick-info">
                      <code>{b.box_code}</code>
                      <span class="muted small">
                        {soVN(b.quantity)} cây
                        {b.mfg_date ? ` · NSX ${fmtDate(b.mfg_date)}` : ""}
                        {b.note ? ` · 📝 ${b.note}` : ""}
                      </span>
                    </span>
                  </label>
                  {checked && (
                    <input
                      class="stock-pick-qty"
                      type="text"
                      inputMode="decimal"
                      value={sel[b.id]}
                      onFocus={(e) => (e.target as HTMLInputElement).select()}
                      onInput={(e) => setQty(b.id, (e.target as HTMLInputElement).value)}
                      title="Số cây lấy từ thùng này"
                    />
                  )}
                </div>
              );
            })}
          </div>
        )}

        {err && <div class="error-banner">{err}</div>}
        <div class="modal-foot">
          <span class={pickedSum >= remaining && remaining > 0 ? "inv-pick-sum ok" : "inv-pick-sum"}>
            Chọn {soVN(pickedSum)}
          </span>
          <button class="btn primary" disabled={busy || !pickedSum} onClick={submit}>
            {busy ? "…" : "Xuất kho"}
          </button>
        </div>
      </div>
    </div>
  );
}
