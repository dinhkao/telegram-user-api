// Lưới ô thùng NHỎ cho card phiếu SX — GIỐNG HỆT nhãn tem (BoxLabelGrid), chỉ nhỏ
// hơn (class .mini). KHÔNG phải link (card đã link tới phiếu) → dùng <span>. 8/hàng.
import { soVN, type KhoBox } from "../api";

// Thùng CÒN HÀNG (không vô hiệu + còn > 0) luôn xếp TRƯỚC (sort ổn định, giữ thứ tự phụ)
const stocked = (b: KhoBox) => (!b.disabled && (b.remaining ?? b.quantity ?? 0) > 0 ? 1 : 0);

export function BoxMiniGrid({ boxes }: { boxes: KhoBox[] }) {
  if (!boxes.length) return null;
  // Cả lưới cùng 1 mã SP (card đã ghi tên SP ở tiêu đề) → BỎ dòng mã trên từng ô
  // (mã dài kiểu K10LV87-KOTEM bị cắt ở cỡ mini); chỉ lưới trộn nhiều SP mới giữ.
  const oneCode = new Set(boxes.map((b) => b.product_code)).size === 1;
  const ordered = boxes.slice().sort((a, b) => stocked(b) - stocked(a));
  return (
    // Lưới trộn nhiều SP giữ dòng mã → 6 ô/hàng (ô rộng hơn, mã dài không bị cắt)
    <div class={"box-mini-grid" + (oneCode ? "" : " mixed")}>
      {ordered.map((b) => {
        const rm = b.remaining ?? b.quantity;
        const st = b.disabled ? "off" : "in";
        const num = (b.box_code || "").split("-").pop() || b.box_code;
        const cap = (b as any).capacity ?? b.quantity;   // SX gốc + hàng nhận chuyển → không tràn
        const fill = cap > 0 ? Math.max(0, Math.min(100, (rm / cap) * 100)) : 100;
        // Thẻ phiếu SX = ghi nhận SẢN XUẤT → số to là số cây NHẬP của thùng
        // (khớp "· N thùng" trên card, không nhảy 0 / 3,04 theo tồn kho); phần
        // CÒN LẠI thể hiện bằng nền fill + mờ ô khi đã cạn (.drained).
        const drained = !b.disabled && rm <= 0;
        return (
          <span key={b.id} class={`box-lbl mini${oneCode ? " nc" : ""} ${st}${drained ? " drained" : ""}`} style={{ "--fill": `${fill}%` } as any}
            title={`${b.box_code} · còn ${soVN(rm)}/${soVN(b.quantity)} ${b.product_unit || ""}`}>
            {!oneCode && <span class="bl-code">{b.product_code}</span>}
            <span class="bl-q">{soVN(b.quantity)}</span>
            <span class="bl-num">{num}</span>
          </span>
        );
      })}
    </div>
  );
}
