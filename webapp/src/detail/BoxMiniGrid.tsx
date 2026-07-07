// Lưới ô thùng NHỎ cho card phiếu SX — GIỐNG HỆT nhãn tem (BoxLabelGrid), chỉ nhỏ
// hơn (class .mini). KHÔNG phải link (card đã link tới phiếu) → dùng <span>. 8/hàng.
import { soVN, type KhoBox } from "../api";

export function BoxMiniGrid({ boxes }: { boxes: KhoBox[] }) {
  if (!boxes.length) return null;
  return (
    <div class="box-mini-grid">
      {boxes.map((b) => {
        const rm = b.remaining ?? b.quantity;
        const st = b.disabled ? "off" : "in";
        const num = (b.box_code || "").split("-").pop() || b.box_code;
        const fill = b.quantity > 0 ? Math.max(0, Math.min(100, (rm / b.quantity) * 100)) : 100;
        // Thẻ phiếu SX = ghi nhận SẢN XUẤT → số to là số cây NHẬP của thùng
        // (khớp "· N thùng" trên card, không nhảy 0 / 3,04 theo tồn kho); phần
        // CÒN LẠI thể hiện bằng nền fill + mờ ô khi đã cạn (.drained).
        const drained = !b.disabled && rm <= 0;
        return (
          <span key={b.id} class={`box-lbl mini ${st}${drained ? " drained" : ""}`} style={{ "--fill": `${fill}%` } as any}
            title={`${b.box_code} · còn ${soVN(rm)}/${soVN(b.quantity)} ${b.product_unit || ""}`}>
            <span class="bl-code">{b.product_code}</span>
            <span class="bl-q">{soVN(b.quantity)}</span>
            <span class="bl-num"><span class="bl-unit">{b.unit_name || "Thùng"}</span> {num}</span>
          </span>
        );
      })}
    </div>
  );
}
