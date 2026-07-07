// Lưới ô thùng SIÊU NHỎ (~8/hàng) cho card phiếu SX. KHÔNG phải link (card đã là
// link tới phiếu) → dùng <span>; chỉ trực quan + tooltip. Nền "bình chứa" theo mức còn.
import { soVN, type KhoBox } from "../api";

export function BoxMiniGrid({ boxes }: { boxes: KhoBox[] }) {
  if (!boxes.length) return null;
  return (
    <div class="box-mini-grid">
      {boxes.map((b) => {
        const rm = b.remaining ?? b.quantity;
        const st = b.disabled ? "off" : "in";
        const fill = b.quantity > 0 ? Math.max(0, Math.min(100, (rm / b.quantity) * 100)) : 100;
        const num = (b.box_code || "").split("-").pop() || b.box_code;
        return (
          <span key={b.id} class={`box-mini ${st}`} style={{ "--fill": `${fill}%` } as any}
            title={`${b.box_code} · ${soVN(rm)}/${soVN(b.quantity)} ${b.product_unit || ""}`}>
            {num}
          </span>
        );
      })}
    </div>
  );
}
