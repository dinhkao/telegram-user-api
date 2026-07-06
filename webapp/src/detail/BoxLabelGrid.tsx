// Lưới nhãn thùng (tem: mã SP · số cây · số thùng, màu theo trạng thái). Dùng chung
// ở KhoBoxes (mọi thùng) + PlaceDetail (thùng 1 vị trí). Tap ô → chi tiết thùng.
import { soVN, type KhoBox } from "../api";

export function BoxLabelGrid({ boxes }: { boxes: KhoBox[] }) {
  return (
    <div class="box-grid lbl-grid">
      {boxes.map((b) => {
        const rm = b.remaining ?? b.quantity;
        const used = b.allocated ?? 0;
        const st = b.disabled ? "off" : used > 0 ? "alloc" : "in";
        const num = (b.box_code || "").split("-").pop() || b.box_code;
        const status = b.disabled ? "vô hiệu" : used > 0 ? `đã xuất ${soVN(used)}/${soVN(b.quantity)}` : "trong kho";
        return (
          <a key={b.id} class={`box-lbl ${st}`} href={`#/thung/${b.id}`}
            title={`${b.box_code} · ${soVN(rm)} cây · ${status}${b.place_name ? ` · ${b.place_name}` : ""}${b.note ? ` · ${b.note}` : ""}`}>
            {b.note && <span class="bl-dot" />}
            {b.place_name && <span class="bl-place">{b.place_name}</span>}
            <span class="bl-code">{b.product_code}</span>
            <span class="bl-q">{soVN(rm)}</span>
            <span class="bl-num">{b.unit_name && b.unit_name !== "Thùng" ? `${b.unit_name} ` : ""}{num}</span>
          </a>
        );
      })}
    </div>
  );
}
