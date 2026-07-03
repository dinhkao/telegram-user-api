// Nhập thùng cho phiếu SX: mỗi lần 1 số cây cho 1 thùng, mã tự sinh (K2L-001).
// POST .../boxes (queueable). onChanged() để phiếu tải lại tổng. Liệt kê thùng đã
// nhập ở phiếu này (GET /api/production/:id/boxes) — tap → chi tiết thùng.
import { useEffect, useState } from "preact/hooks";
import { addProductionBoxes, slipBoxes, soVN, type ProdSlip, type InvBox } from "../api";

const STATUS: Record<string, { label: string; cls: string }> = {
  in_stock: { label: "Trong kho", cls: "in" },
  allocated: { label: "Đã xuất", cls: "alloc" },
  shipped: { label: "Đã giao", cls: "ship" },
};

export function ProductionBoxes({
  threadId,
  slip,
  onChanged,
}: {
  threadId: string;
  slip: ProdSlip;
  onChanged: () => void;
}) {
  const hasSp = !!slip.sp_name;
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [myBoxes, setMyBoxes] = useState<InvBox[]>([]);

  const loadMine = async () => {
    try {
      setMyBoxes(await slipBoxes(threadId));
    } catch {
      /* im lặng */
    }
  };
  useEffect(() => {
    loadMine();
  }, [slip.sp_name, slip.total]);

  const submit = async () => {
    const n = parseFloat(amount.replace(",", "."));
    if (!isFinite(n) || n <= 0) {
      setMsg("Số cây không hợp lệ");
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const r = await addProductionBoxes(threadId, [{ quantity: n }], note.trim());
      setAmount("");
      setNote("");
      if (r?._queued) {
        setMsg("⏳ Đã lưu tạm (mất mạng), sẽ gửi lại");
      } else {
        setMsg("✅ Đã nhập 1 thùng");
        onChanged();
        loadMine();
      }
    } catch (e: any) {
      setMsg(e?.message || "Lỗi nhập thùng");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section class="card">
      <label class="card-label">📦 Nhập thùng {slip.sp_name ? `(${slip.sp_name})` : ""}</label>
      {!hasSp && <div class="muted small">Chọn sản phẩm trước khi nhập.</div>}

      <div class="row">
        <input
          type="text"
          inputMode="decimal"
          value={amount}
          disabled={!hasSp}
          onInput={(e) => setAmount((e.target as HTMLInputElement).value)}
          placeholder="Số cây trong thùng"
        />
        <input
          type="text"
          value={note}
          disabled={!hasSp}
          onInput={(e) => setNote((e.target as HTMLInputElement).value)}
          placeholder="Ghi chú (tuỳ chọn)"
        />
        <button class="btn primary" disabled={!hasSp || busy} onClick={submit}>
          {busy ? "…" : "＋"}
        </button>
      </div>
      {msg && <div class="muted small">{msg}</div>}

      {myBoxes.length > 0 && (
        <div class="inv-summary">
          <div class="inv-total">Thùng nhập ở phiếu này ({myBoxes.length})</div>
          <div class="inv-detail-list">
            {myBoxes.map((b) => {
              const st = STATUS[b.status] || { label: b.status, cls: "" };
              const tail = b.order_thread_id ? ` #${b.order_thread_id}` : "";
              return (
                <a key={b.id} id={`box-${b.id}`} class="inv-detail-row link" href={`#/thung/${b.id}`}>
                  <code class="inv-bc">{b.box_code}</code>
                  <span class="inv-q">{soVN(b.quantity)}</span>
                  <span class={`inv-status ${st.cls}`}>
                    {st.label}
                    {tail}
                  </span>
                </a>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
