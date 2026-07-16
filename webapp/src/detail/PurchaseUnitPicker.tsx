// Ô chọn ĐƠN VỊ NHẬP cho 1 dòng phiếu nhập hàng (PurchaseModal + PurchaseEdit).
// Hiện khi SP có trong danh mục (đã nạp đơn vị gốc); SP chưa có quy đổi vẫn có chỗ
// chọn + option "➕ Thêm đơn vị quy đổi…" tạo ngay trong popup (addUnitChoice →
// product_units, quyền văn phòng — cùng gate với tạo phiếu). SL + giá của dòng
// tính theo đơn vị đã chọn; kèm nhãn "= X <gốc>" để khỏi nhầm.
import { useState } from "preact/hooks";
import { soVN } from "../api";
import { SelectPopup } from "../ui/SelectPopup";
import { toast } from "../ui/feedback";
import { addUnitChoice, type UnitChoice } from "./purchaseProduct";

const ADD = "__add__";

export function PurchaseUnitPicker({ code, line, choices, onPick, onChoices }: {
  code: string;                                        // mã SP của dòng (để thêm quy đổi)
  line: { unit?: string; factor?: number; sl: string };
  choices?: UnitChoice[];
  onPick: (u: UnitChoice) => void;
  onChoices?: (code: string, list: UnitChoice[]) => void;   // list mới sau khi thêm đơn vị
}) {
  const [adding, setAdding] = useState(false);
  const [nName, setNName] = useState("");
  const [nFactor, setNFactor] = useState("");
  const [busy, setBusy] = useState(false);
  if (!choices || !choices.length) return null;       // SP chưa chọn / ngoài danh mục
  const base = choices[0];                            // phần tử đầu = đơn vị gốc (factor 1)
  const cur = line.unit || base.name;
  const sl = parseFloat((line.sl || "").replace(",", ".")) || 0;

  const saveNew = async () => {
    const f = Number(nFactor.replace(",", "."));
    if (!nName.trim() || !f || f <= 0) { toast("Nhập tên đơn vị + tỉ lệ > 0", "err"); return; }
    setBusy(true);
    try {
      const list = await addUnitChoice(code, nName.trim(), f);
      onChoices?.(code.trim().toUpperCase(), list);
      const u = list.find((c) => c.name === nName.trim());
      if (u) onPick(u);
      setAdding(false); setNName(""); setNFactor("");
      toast("Đã thêm đơn vị quy đổi", "ok");
    } catch (e: any) {
      toast(e?.message || "Lỗi thêm đơn vị", "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="pu-unit-row">
      <span class="muted small">Đơn vị nhập:</span>
      <SelectPopup title="Đơn vị nhập (SL + giá tính theo đơn vị này)" value={cur}
        options={[
          ...choices.map((c) => ({
            value: c.name, label: c.name,
            sub: c.factor !== 1 ? `1 ${c.name} = ${soVN(c.factor)} ${base.name}` : "đơn vị gốc",
          })),
          { value: ADD, label: "➕ Thêm đơn vị quy đổi…", sub: `ví dụ: 1 Thùng = 30 ${base.name}` },
        ]}
        onChange={(v) => {
          if (v === ADD) { setAdding(true); return; }
          const u = choices.find((c) => c.name === v);
          if (u) onPick(u);
        }} />
      {line.unit && (line.factor || 0) > 0 && sl > 0 && (
        <span class="muted small">= {soVN(sl * (line.factor || 1))} {base.name}</span>
      )}
      {adding && (
        <div class="pu-unit-add">
          <span class="muted small">1</span>
          <input type="text" placeholder="Thùng…" value={nName}
            onInput={(e) => setNName((e.target as HTMLInputElement).value)} />
          <span class="muted small">=</span>
          <input type="text" inputMode="decimal" placeholder="30" value={nFactor}
            onInput={(e) => setNFactor((e.target as HTMLInputElement).value)} />
          <span class="muted small">{base.name}</span>
          <button class="btn small primary" disabled={busy} onClick={saveNew}>{busy ? "…" : "OK"}</button>
          <button class="btn small" onClick={() => { setAdding(false); setNName(""); setNFactor(""); }}>Huỷ</button>
        </div>
      )}
    </div>
  );
}
