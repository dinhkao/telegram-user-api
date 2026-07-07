// Lưới ô thùng NHỎ cho card phiếu SX — GIỐNG HỆT nhãn tem (BoxLabelGrid), chỉ nhỏ
// hơn (class .mini). KHÔNG phải link (card đã link tới phiếu) → dùng <span>. 8/hàng.
import { soVN, type KhoBox } from "../api";

export function BoxMiniGrid({ boxes }: { boxes: KhoBox[] }) {
  if (!boxes.length) return null;
  return (
    <div class="box-mini-grid">
      {boxes.map((b) => {
        const rm = b.remaining ?? b.quantity;
        const used = b.allocated ?? 0;
        const st = b.disabled ? "off" : "in";
        const num = (b.box_code || "").split("-").pop() || b.box_code;
        const fill = b.quantity > 0 ? Math.max(0, Math.min(100, (rm / b.quantity) * 100)) : 100;
        return (
          <span key={b.id} class={`box-lbl mini ${st}`} style={{ "--fill": `${fill}%` } as any}
            title={`${b.box_code} · ${soVN(rm)}/${soVN(b.quantity)} ${b.product_unit || ""}`}>
            <span class="bl-code">{b.product_code}</span>
            <span class="bl-q">{soVN(rm)}{used > 0 ? <span class="bl-q-tot">/{soVN(b.quantity)}</span> : ""}</span>
            <span class="bl-num"><span class="bl-unit">{b.unit_name || "Thùng"}</span> {num}</span>
          </span>
        );
      })}
    </div>
  );
}
