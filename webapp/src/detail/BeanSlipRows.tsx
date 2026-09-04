// Card PHIẾU KHO ĐẬU dùng chung — danh sách phiếu (#/kho-dau/phieu) và các trang
// chi tiết loại đậu / kho. Viền trái theo loại phiếu; dòng gõ bằng đơn vị quy đổi
// hiện cả 2 số ("2 bao (100 kg)"). Nối: api.BeanSlip.
import { soVN, BEAN_KIND_LABEL, type BeanSlip, type BeanSlipKind } from "../api";
import { fmtHourVN } from "../format";
import { Icon } from "../ui/Icon";

const KIND_ICON: Record<BeanSlipKind, string> = {
  nhap: "plus", xuat: "truck", dieu_chinh: "edit", chuyen: "refresh",
};

/** Dấu +/−/± trước tổng biến động (điều chỉnh có thể lên hoặc xuống).
 *  Phiếu CHUYỂN: items là phía kho nguồn (delta âm) nhưng tồn TỔNG không đổi
 *  → hiện số lượng chuyển KHÔNG dấu. */
export function slipDeltaText(items: BeanSlip["items"], kind?: BeanSlipKind): string {
  const sum = items.reduce((t, i) => t + (i.delta || 0), 0);
  if (kind === "chuyen") return soVN(Math.abs(sum));
  return (sum > 0 ? "+" : sum < 0 ? "−" : "") + soVN(Math.abs(sum));
}

const lineText = (i: BeanSlip["items"][number], withBean = true) => {
  const head = withBean ? `${i.bean_name} ` : "";
  return i.converted
    ? `${head}${soVN(i.entered_qty)} ${i.entered_unit} (${soVN(i.quantity)} ${i.unit})`
    : `${head}${soVN(i.quantity)}${i.unit ? " " + i.unit : ""}`;
};

/** Giờ tạo phiếu; kèm ngày khi danh sách KHÔNG gom theo ngày.
 *  Ngày lấy từ `ymd` (server đã chốt theo giờ VN), giờ qua `fmtHourVN` — đừng cắt
 *  chuỗi `created_at` vì nó lưu UTC. */
function slipTimeText(slip: BeanSlip, showDate: boolean): string {
  const hour = fmtHourVN(slip.created_at);
  const m = showDate ? String(slip.ymd || "").match(/^(\d{4})-(\d{2})-(\d{2})$/) : null;
  const date = m ? `${m[3]}/${m[2]}` : "";
  return [date, hour].filter(Boolean).join(" ");
}

export function BeanSlipCard({ slip, showPlace = true, showBean = true, showDate = true, beanId }: {
  slip: BeanSlip;
  /** Trang chi tiết KHO thì khỏi lặp lại tên kho ở mọi dòng. */
  showPlace?: boolean;
  /** Trang chi tiết LOẠI ĐẬU thì khỏi lặp lại tên đậu. */
  showBean?: boolean;
  /** Danh sách đã gom theo ngày (#/kho-dau/phieu) thì chỉ hiện giờ. */
  showDate?: boolean;
  /** Trang chi tiết LOẠI ĐẬU: chỉ hiện dòng + tổng +/− của đậu này (phiếu chung
   *  nhiều loại đậu thì các loại khác gom thành "+N loại khác"). */
  beanId?: number;
}) {
  const time = slipTimeText(slip, showDate);
  const items = beanId ? slip.items.filter((i) => i.bean_id === beanId) : slip.items;
  const others = slip.items.length - items.length;
  return (
    <a class={"bean-slip-card k-" + slip.kind} href={`#/kho-dau/phieu/${slip.id}`}>
      <div class="bean-slip-top">
        <span class="bean-slip-kind">
          <Icon name={KIND_ICON[slip.kind]} size={14} /> {BEAN_KIND_LABEL[slip.kind]}
        </span>
        {time ? <span class="bean-slip-time muted small">{time}</span> : null}
        <span class="bean-slip-amt">{slipDeltaText(items, slip.kind)}</span>
      </div>
      <div class="bean-slip-sub muted small">
        {/* Phiếu chuyển luôn ghi cả 2 đầu — trang chi tiết 1 kho vẫn cần biết đầu kia */}
        {slip.kind === "chuyen" && slip.dest_place_name
          ? `${slip.place_name} → ${slip.dest_place_name} · `
          : showPlace ? `${slip.place_name} · ` : ""}
        {items.map((i) => lineText(i, showBean)).join(", ")}
        {others > 0 ? ` (+${others} loại khác)` : ""}
        {slip.partner ? ` · ${slip.partner}` : ""}
        {slip.created_by ? ` · ${slip.created_by}` : ""}
      </div>
      {slip.note ? <div class="bean-slip-note muted small">“{slip.note}”</div> : null}
    </a>
  );
}
