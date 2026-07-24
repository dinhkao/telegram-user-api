// Trang #/usage (admin) — thống kê mức dùng tính năng webapp: trang nào vào nhiều,
// nút nào bấm nhiều/ít nhất. Dữ liệu = đếm gộp theo ngày (usage_store, client gửi
// batch từ src/usage.ts). Nối: GET /api/usage/stats.
import { useEffect, useState } from "preact/hooks";
import { getJSON } from "../api";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { EmptyState, ErrorState, Loading } from "../ui/states";

type PageRow = { page: string; views: number; taps: number };
type LabelRow = { page: string; label: string; count: number };
type UserRow = { username: string; views: number; taps: number };
type Stats = { days: number; since: string; pages: PageRow[]; labels: LabelRow[]; users: UserRow[] };

// Tên tiếng Việt cho route chính — route lạ hiện nguyên văn.
const ROUTE_NAMES: Record<string, string> = {
  "#/": "Đơn hàng", "#/orders": "Đơn hàng", "#/order/:id": "Chi tiết đơn",
  "#/order/:id/hoa-don": "Sửa hoá đơn", "#/create": "Tạo đơn",
  "#/customers": "Khách hàng", "#/khach/:id": "Chi tiết khách", "#/khach/:id/lich": "Lịch khách",
  "#/tra-hang": "Trả hàng", "#/tra-hang/:id": "Chi tiết trả hàng",
  "#/lich": "Lịch giao", "#/dang-giao": "Đang giao", "#/viec": "Việc", "#/viec/:id": "Chi tiết việc",
  "#/kho": "Kho hàng", "#/kho/:id": "Chi tiết SP kho", "#/thung/:id": "Chi tiết thùng",
  "#/nhap-hang": "Nhập hàng", "#/nhap-hang/:id": "Chi tiết phiếu nhập", "#/ncc": "Nhà cung cấp",
  "#/nhu-cau": "Cần làm hàng", "#/chuyen-kho": "Chuyển kho", "#/san-pham": "Sản phẩm",
  "#/xuat-huy": "Xuất hủy", "#/xuat-huy/:id": "Chi tiết phiếu hủy",
  "#/dieu-chinh": "Điều chỉnh tồn",
  "#/vi-tri": "Vị trí kho", "#/so-thung": "Số thùng",
  "#/san_xuat": "Phiếu sản xuất", "#/san_xuat/:id": "Chi tiết phiếu SX",
  "#/san_xuat/:id/bao-cao": "Sửa báo cáo SX", "#/sx-bang": "Dashboard SX", "#/tho": "Danh sách thợ",
  "#/tien-cong": "Tiền công thợ", "#/bao-cao": "Báo cáo SX", "#/luong-sp": "Lương sản phẩm",
  "#/quy": "Sổ quỹ", "#/bang-gia": "Bảng giá", "#/camera": "Camera",
  "#/lich-su": "Lịch sử thao tác", "#/home": "Menu Thêm", "#/thu-tien": "Thu tiền",
  "#/login": "Đăng nhập / Cài đặt", "#/users": "Quản lý user", "#/usage": "Thống kê sử dụng",
};
const pageName = (page: string) => ROUTE_NAMES[page] || page;

export function UsageStats() {
  const [days, setDays] = useState(30);
  const [user, setUser] = useState("");
  const [data, setData] = useState<Stats | null>(null);
  const [error, setError] = useState("");

  const load = () => {
    setData(null);
    setError("");
    const query = new URLSearchParams({ days: String(days) });
    if (user) query.set("user", user);
    getJSON(`/api/usage/stats?${query}`, { cache: false })
      .then(setData)
      .catch((reason: any) => setError(reason?.message || "Không tải được thống kê"));
  };
  useEffect(() => { load(); }, [days, user]);

  if (error) return <div class="usage-page"><PageHead fallback="#/home" title="Thống kê sử dụng" /><ErrorState msg={error} onRetry={load} /></div>;
  if (!data) return <div class="usage-page"><PageHead fallback="#/home" title="Thống kê sử dụng" /><Loading label="Đang tổng hợp…" /></div>;

  const maxPage = Math.max(1, ...data.pages.map((p) => p.views + p.taps));
  const topLabels = data.labels.slice(0, 30);
  const maxLabel = Math.max(1, topLabels[0]?.count || 0);
  // Ít dùng nhất: lấy từ đáy danh sách (đã sort giảm dần), đảo lại cho dễ đọc.
  const rareLabels = data.labels.slice(-15).reverse();

  return (
    <div class="usage-page">
      <PageHead fallback="#/home" title="Thống kê sử dụng" />
      <div class="chips">
        {[7, 30, 90].map((d) => (
          <button class={"chip" + (days === d ? " active" : "")} key={d} onClick={() => setDays(d)}>{d} ngày</button>
        ))}
      </div>
      {data.users.length > 1 && (
        <div class="chips">
          <button class={"chip" + (!user ? " active" : "")} onClick={() => setUser("")}>Mọi người</button>
          {data.users.map((u) => (
            <button class={"chip" + (user === u.username ? " active" : "")} key={u.username} onClick={() => setUser(u.username)}>
              {u.username} · {u.taps}
            </button>
          ))}
        </div>
      )}

      <section class="usage-sec">
        <label class="card-label"><Icon name="chart" size={16} /> Tính năng dùng nhiều → ít <small>từ {data.since}</small></label>
        {data.pages.length === 0 && <EmptyState icon="📊">Chưa có dữ liệu — dùng app một lúc rồi quay lại.</EmptyState>}
        {data.pages.map((p) => (
          <div class="usage-row" key={p.page}>
            <i style={`width:${Math.max(2, Math.round((p.views + p.taps) / maxPage * 100))}%`} />
            <b>{pageName(p.page)}</b>
            <span>{p.views} lượt vào · {p.taps} bấm</span>
          </div>
        ))}
      </section>

      <section class="usage-sec">
        <label class="card-label"><Icon name="check" size={16} /> Nút bấm nhiều nhất</label>
        {topLabels.map((l) => (
          <div class="usage-row" key={l.page + l.label}>
            <i style={`width:${Math.max(2, Math.round(l.count / maxLabel * 100))}%`} />
            <b>{l.label}</b>
            <span>{pageName(l.page)} · {l.count}</span>
          </div>
        ))}
      </section>

      {rareLabels.length > 0 && data.labels.length > 30 && (
        <section class="usage-sec">
          <label class="card-label"><Icon name="minus" size={16} /> Ít bấm nhất</label>
          {rareLabels.map((l) => (
            <div class="usage-row rare" key={l.page + l.label}>
              <b>{l.label}</b>
              <span>{pageName(l.page)} · {l.count}</span>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
