// Nhập thùng cho phiếu SX: mỗi thùng số cây tự do, mã tự sinh (K2L-001). Xem tồn
// kho product (nhóm theo size: 5 thùng 50, x thùng 70…). POST .../boxes (queueable).
// onChanged() để phiếu tải lại tổng. Nguồn tồn: GET /api/inventory/:code.
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
  const [rows, setRows] = useState<string[]>([""]);
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

  const setRow = (i: number, v: string) => setRows(rows.map((r, j) => (j === i ? v : r)));
  const addRow = () => setRows([...rows, ""]);
  const rmRow = (i: number) => setRows(rows.length > 1 ? rows.filter((_, j) => j !== i) : [""]);

  const validCount = rows.filter((r) => {
    const n = parseFloat(r.replace(",", "."));
    return isFinite(n) && n > 0;
  }).length;

  const submit = async () => {
    const qs = rows
      .map((r) => parseFloat(r.replace(",", ".")))
      .filter((n) => isFinite(n) && n > 0);
    if (!qs.length) {
      setMsg("Nhập số cây cho ít nhất 1 thùng");
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const r = await addProductionBoxes(threadId, qs.map((q) => ({ quantity: q })), note.trim());
      setRows([""]);
      setNote("");
      if (r?._queued) {
        setMsg("⏳ Đã lưu tạm (mất mạng), sẽ gửi lại");
      } else {
        setMsg(`✅ Đã nhập ${qs.length} thùng`);
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

      {rows.map((v, i) => (
        <div class="row" key={i}>
          <input
            type="text"
            inputMode="decimal"
            value={v}
            disabled={!hasSp}
            onInput={(e) => setRow(i, (e.target as HTMLInputElement).value)}
            placeholder={`Thùng ${i + 1} — số cây`}
          />
          <button class="btn" disabled={!hasSp} onClick={() => rmRow(i)} title="Bỏ thùng">
            －
          </button>
        </div>
      ))}

      <div class="row">
        <button class="btn" disabled={!hasSp} onClick={addRow}>
          ＋ Thêm thùng
        </button>
        <input
          type="text"
          value={note}
          disabled={!hasSp}
          onInput={(e) => setNote((e.target as HTMLInputElement).value)}
          placeholder="Ghi chú đợt (tuỳ chọn)"
        />
      </div>

      <button class="btn primary block" disabled={!hasSp || busy} onClick={submit}>
        {busy ? "…" : `Nhập ${validCount || ""} thùng`}
      </button>
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
