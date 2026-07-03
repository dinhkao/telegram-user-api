// Nhập thùng cho phiếu SX: mỗi thùng số cây tự do, mã tự sinh (K2L-001). Xem tồn
// kho product (nhóm theo size: 5 thùng 50, x thùng 70…). POST .../boxes (queueable).
// onChanged() để phiếu tải lại tổng. Nguồn tồn: GET /api/inventory/:code.
import { useEffect, useState } from "preact/hooks";
import { addProductionBoxes, inventoryDetail, soVN, type ProdSlip, type InvDetail } from "../api";

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
  const [inv, setInv] = useState<InvDetail | null>(null);
  const [showBoxes, setShowBoxes] = useState(false);

  const loadInv = async () => {
    if (!slip.sp_name) {
      setInv(null);
      return;
    }
    try {
      setInv(await inventoryDetail(slip.sp_name));
    } catch {
      /* im lặng — tồn kho là phụ */
    }
  };
  useEffect(() => {
    loadInv();
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
        loadInv();
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

      {inv && inv.box_count > 0 && (
        <div class="inv-summary">
          <div class="inv-total">
            Tồn kho: <b>{soVN(inv.total)}</b> ({inv.box_count} thùng)
          </div>
          <div class="inv-groups">
            {inv.groups.map((g) => (
              <span class="inv-chip" key={g.quantity}>
                {g.count} thùng × {soVN(g.quantity)}
              </span>
            ))}
          </div>
          <button class="btn small" onClick={() => setShowBoxes(!showBoxes)}>
            {showBoxes ? "Ẩn mã thùng" : "Xem mã thùng"}
          </button>
          {showBoxes && (
            <ul class="inv-box-list">
              {inv.boxes.map((b) => (
                <li key={b.id}>
                  <code>{b.box_code}</code> · {soVN(b.quantity)}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
