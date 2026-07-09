// Lưới nhãn thùng (tem: mã SP · số cây · số thùng, màu theo trạng thái). Dùng chung
// ở KhoBoxes (mọi thùng) + PlaceDetail (thùng 1 vị trí). Tap ô → chi tiết thùng.
import { soVN, type KhoBox } from "../api";

// Thùng CÒN HÀNG (không vô hiệu + còn > 0) luôn xếp TRƯỚC — áp cho MỌI view dùng
// lưới này. Sort ổn định nên giữ nguyên thứ tự phụ mà caller đã sắp.
const stocked = (b: KhoBox) => (!b.disabled && (b.remaining ?? b.quantity ?? 0) > 0 ? 1 : 0);

export function BoxLabelGrid({ boxes }: { boxes: KhoBox[] }) {
  const ordered = boxes.slice().sort((a, b) => stocked(b) - stocked(a));
  return (
    <div class="box-grid lbl-grid">
      {ordered.map((b) => {
        const rm = b.remaining ?? b.quantity;
        const used = b.allocated ?? 0;
        // Luôn XANH (như đầy); mức nền thể hiện phần còn lại. Chỉ vô hiệu mới khác màu.
        const st = b.disabled ? "off" : "in";
        const num = (b.box_code || "").split("-").pop() || b.box_code;
        const status = b.disabled ? "vô hiệu" : used > 0 ? `đã xuất ${soVN(used)}/${soVN(b.quantity)}` : "trong kho";
        // Mức "bình chứa": nền đổ đầy theo remaining/gốc
        const fillPct = b.quantity > 0 ? Math.max(0, Math.min(100, (rm / b.quantity) * 100)) : 100;
        return (
          <a key={b.id} class={`box-lbl ${st}`} href={`#/thung/${b.id}`} style={{ "--fill": `${fillPct}%` } as any}
            title={`${b.box_code} · ${soVN(rm)} ${b.product_unit || "cây"} · ${status}${b.place_name ? ` · ${b.place_name}` : ""}${b.note ? ` · ${b.note}` : ""}`}>
            {b.note && <span class="bl-dot" />}
            <span class="bl-code">{b.product_code}</span>
            <span class="bl-q">{soVN(rm)}{used > 0 ? <span class="bl-q-tot">/{soVN(b.quantity)}</span> : ""}</span>
            <span class="bl-num">{num}</span>
          </a>
        );
      })}
    </div>
  );
}
