// Nút chọn ĐƠN VỊ NHẬP đứng cạnh ô số lượng (chuyển hàng / xuất hủy / điều chỉnh
// tồn — BoxDetail, BoxAdjust). Lựa chọn = đơn vị GỐC + các đơn vị quy đổi của SP
// (unitChoicesFor — cache module, cùng nguồn phiếu nhập). Parent giữ unit đã chọn;
// SỐ NHẬP × factor = số ĐƠN VỊ GỐC gửi API — server luôn nhận hệ gốc, không đổi gì.
// SP không có đơn vị quy đổi → nhãn tĩnh đơn vị gốc như cũ.
import { useEffect, useState } from "preact/hooks";
import { SelectPopup } from "../ui/SelectPopup";
import { soVN } from "../api";
import { unitChoicesFor, type UnitChoice } from "./purchaseProduct";

export type { UnitChoice };

export const baseChoice = (name?: string | null): UnitChoice => ({ name: (name || "cây").trim() || "cây", factor: 1 });

/** Số đã nhập (theo đơn vị chọn) → số ĐƠN VỊ GỐC; NaN giữ NaN để check hợp lệ như cũ. */
export const toBaseQty = (raw: number, unit: UnitChoice): number => raw * (unit.factor || 1);

export function QtyUnitPicker({ code, baseUnit, unit, onPick }: {
  code: string; baseUnit?: string | null; unit: UnitChoice; onPick: (u: UnitChoice) => void;
}) {
  const [choices, setChoices] = useState<UnitChoice[]>([]);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    let live = true;
    unitChoicesFor(code).then((cs) => { if (live) setChoices(cs); }).catch(() => {});
    return () => { live = false; };
  }, [code]);
  if (choices.length <= 1) return <span class="qty-unit-static">{unit.name}</span>;
  return (
    <>
      <button type="button" class="qty-unit-btn" title="Nhập theo đơn vị nào?" onClick={() => setOpen(true)}>
        {unit.name} ▾
      </button>
      <SelectPopup open={open} onClose={() => setOpen(false)} title="Nhập theo đơn vị"
        value={unit.name}
        options={choices.map((c) => ({
          value: c.name, label: c.name,
          sub: c.factor === 1 ? "đơn vị gốc" : `1 ${c.name} = ${soVN(c.factor)} ${baseUnit || "cây"}`,
        }))}
        onChange={(v) => { const c = choices.find((x) => x.name === v); if (c) onPick(c); }} />
    </>
  );
}
