// Ô chọn ĐƠN VỊ NHẬP cho 1 dòng phiếu nhập hàng (PurchaseModal + PurchaseEdit).
// Chỉ hiện khi SP có đơn vị quy đổi (product_units — xem detail/ProductUnits).
// SL + giá của dòng tính theo đơn vị đã chọn; kèm nhãn "= X <gốc>" để khỏi nhầm.
import { soVN } from "../api";
import { SelectPopup } from "../ui/SelectPopup";
import type { UnitChoice } from "./purchaseProduct";

export function PurchaseUnitPicker({ line, choices, onPick }: {
  line: { unit?: string; factor?: number; sl: string };
  choices?: UnitChoice[];
  onPick: (u: UnitChoice) => void;
}) {
  if (!choices || choices.length < 2) return null;   // SP không có quy đổi → nhập theo gốc như cũ
  const base = choices[0];                            // phần tử đầu = đơn vị gốc (factor 1)
  const cur = line.unit || base.name;
  const sl = parseFloat((line.sl || "").replace(",", ".")) || 0;
  return (
    <div class="pu-unit-row">
      <span class="muted small">Đơn vị nhập:</span>
      <SelectPopup title="Đơn vị nhập (SL + giá tính theo đơn vị này)" value={cur}
        options={choices.map((c) => ({
          value: c.name, label: c.name,
          sub: c.factor !== 1 ? `1 ${c.name} = ${soVN(c.factor)} ${base.name}` : "đơn vị gốc",
        }))}
        onChange={(v) => { const u = choices.find((c) => c.name === v); if (u) onPick(u); }} />
      {line.unit && (line.factor || 0) > 0 && sl > 0 && (
        <span class="muted small">= {soVN(sl * (line.factor || 1))} {base.name}</span>
      )}
    </div>
  );
}
