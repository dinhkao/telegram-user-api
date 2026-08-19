// Card PHIẾU KHO ĐẬU dùng chung — danh sách phiếu (#/kho-dau/phieu) và các trang
// chi tiết loại đậu / kho. Viền trái theo loại phiếu; dòng gõ bằng đơn vị quy đổi
// hiện cả 2 số ("2 bao (100 kg)"). Nối: api.BeanSlip.
import { soVN, BEAN_KIND_LABEL, type BeanSlip, type BeanSlipKind } from "../api";
import { fmtHourVN } from "../format";
import { Icon } from "../ui/Icon";

const KIND_ICON: Record<BeanSlipKind, string> = {
  nhap: "plus", xuat: "truck", dieu_chinh: "edit",
};

/** Dấu +/−/± trước tổng biến động của phiếu (điều chỉnh có thể lên hoặc xuống). */
export function slipDeltaText(s: BeanSlip): string {
  const sum = s.items.reduce((t, i) => t + (i.delta || 0), 0);
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

export function BeanSlipCard({ slip, showPlace = true, showBean = true, showDate = true }: {
  slip: BeanSlip;
  /** Trang chi tiết KHO thì khỏi lặp lại tên kho ở mọi dòng. */
  showPlace?: boolean;
  /** Trang chi tiết LOẠI ĐẬU thì khỏi lặp lại tên đậu. */
  showBean?: boolean;
  /** Danh sách đã gom theo ngày (#/kho-dau/phieu) thì chỉ hiện giờ. */
  showDate?: boolean;
}) {
  const time = slipTimeText(slip, showDate);
  return (
    <a class={"bean-slip-card k-" + slip.kind} href={`#/kho-dau/phieu/${slip.id}`}>
      <div class="bean-slip-top">
        <span class="bean-slip-kind">
          <Icon name={KIND_ICON[slip.kind]} size={14} /> {BEAN_KIND_LABEL[slip.kind]}
        </span>
        {time ? <span class="bean-slip-time muted small">{time}</span> : null}
        <span class="bean-slip-amt">{slipDeltaText(slip)}</span>
      </div>
      <div class="bean-slip-sub muted small">
        {showPlace ? `${slip.place_name} · ` : ""}
        {slip.items.map((i) => lineText(i, showBean)).join(", ")}
        {slip.partner ? ` · ${slip.partner}` : ""}
        {slip.created_by ? ` · ${slip.created_by}` : ""}
      </div>
      {slip.note ? <div class="bean-slip-note muted small">“{slip.note}”</div> : null}
    </a>
  );
}
