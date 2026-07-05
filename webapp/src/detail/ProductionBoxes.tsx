// Nhập thùng cho phiếu SX: 1 đợt = N thùng GIỐNG NHAU (cùng số cây), mã tự sinh
// (K2L-001). POST .../boxes (queueable, gửi mảng {quantity} × số thùng). onChanged()
// để phiếu tải lại tổng. Liệt kê thùng đã nhập ở phiếu này — tap → chi tiết thùng.
import { useEffect, useState } from "preact/hooks";
import { addProductionBoxes, slipBoxes, soVN, type ProdSlip, type InvBox } from "../api";
import { onRealtime } from "../realtime";

function todayLocal(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

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
  const [count, setCount] = useState("1");
  const [note, setNote] = useState("");
  const [mfgDate, setMfgDate] = useState(todayLocal());
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
  // Realtime: thùng đổi ở nơi khác (sửa ghi chú/số cây/vô hiệu/xuất) không luôn đổi
  // slip.total → tự tải lại list thùng của phiếu này.
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "box_changed" || e.type === "inventory_changed" || e.type === "resync") {
        clearTimeout(t); t = setTimeout(loadMine, 300);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, [threadId]);

  const submit = async () => {
    const n = parseFloat(amount.replace(",", "."));
    if (!isFinite(n) || n <= 0) {
      setMsg("Số cây không hợp lệ");
      return;
    }
    const c = Math.floor(parseFloat(count.replace(",", ".")));
    if (!isFinite(c) || c <= 0) {
      setMsg("Số thùng không hợp lệ");
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const picks = Array.from({ length: c }, () => ({ quantity: n }));  // c thùng giống nhau
      const r = await addProductionBoxes(threadId, picks, note.trim(), mfgDate);
      setAmount("");
      setCount("1");
      setNote("");
      if (r?._queued) {
        setMsg("⏳ Đã lưu tạm (mất mạng), sẽ gửi lại");
      } else {
        setMsg(`✅ Đã nhập ${c} thùng`);
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
        <label class="inline-label">📅 NSX</label>
        <input
          type="date"
          value={mfgDate}
          disabled={!hasSp}
          onInput={(e) => setMfgDate((e.target as HTMLInputElement).value)}
        />
      </div>
      <div class="row">
        <input
          type="text"
          inputMode="decimal"
          class="pb-amount"
          value={amount}
          disabled={!hasSp}
          onFocus={(e) => (e.target as HTMLInputElement).select()}
          onInput={(e) => setAmount((e.target as HTMLInputElement).value)}
          placeholder="Số cây / thùng"
        />
        <span class="pb-x">×</span>
        <input
          type="text"
          inputMode="numeric"
          class="pb-count"
          value={count}
          disabled={!hasSp}
          onFocus={(e) => (e.target as HTMLInputElement).select()}
          onInput={(e) => setCount((e.target as HTMLInputElement).value)}
          placeholder="Số thùng"
          title="Số thùng giống nhau"
        />
      </div>
      <div class="row">
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
              const rem = b.remaining ?? b.quantity;
              const used = b.allocated ?? 0;
              return (
                <a
                  key={b.id}
                  id={`box-${b.id}`}
                  class={b.disabled ? "inv-detail-row link box-off" : "inv-detail-row link"}
                  href={`#/thung/${b.id}`}
                >
                  <code class="inv-bc">{b.box_code}</code>
                  <span class="inv-q">
                    {soVN(rem)}
                    {used > 0 ? <span class="muted">/{soVN(b.quantity)}</span> : ""}
                  </span>
                  {b.note && <span class="inv-note muted small">📝 {b.note}</span>}
                  {b.disabled ? (
                    <span class="inv-status disabled" title={b.disabled_reason || undefined}>
                      Vô hiệu
                    </span>
                  ) : used > 0 ? (
                    <span class="inv-status alloc">đã xuất {soVN(used)}</span>
                  ) : (
                    <span class="inv-status in">Trong kho</span>
                  )}
                </a>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
