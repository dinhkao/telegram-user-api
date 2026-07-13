// Trang chủ (#/home) — mọi mục của app gom theo NHÓM liên quan, mỗi mục 1 ô bấm được.
// Thay menu "Mục khác" dài (bị cắt) bằng trang cuộn được, có phân nhóm. Vào từ nút ☰
// Thêm ở thanh điều hướng. Mục theo quyền: office = admin/van_phong, admin = admin.
import { currentUser } from "../api";
import { Icon } from "../ui/Icon";

type Item = { label: string; href: string; icon: string; office?: boolean; admin?: boolean };
type Group = { title: string; icon: string; items: Item[] };

const GROUPS: Group[] = [
  { title: "Đơn hàng", icon: "clipboard", items: [
    { label: "Đơn hàng", href: "#/orders", icon: "clipboard" },
    { label: "Tạo đơn", href: "#/create", icon: "plus" },
    { label: "Khách hàng", href: "#/customers", icon: "user" },
    { label: "Trả hàng", href: "#/tra-hang", icon: "refresh" },
    { label: "Lịch giao", href: "#/lich", icon: "calendar" },
    { label: "Đang giao", href: "#/dang-giao", icon: "truck" },
    { label: "Việc", href: "#/viec", icon: "check" },
  ] },
  { title: "Kho", icon: "box", items: [
    { label: "Kho hàng", href: "#/kho", icon: "box" },
    { label: "Nhập hàng", href: "#/nhap-hang", icon: "truck" },
    { label: "Nhà cung cấp", href: "#/ncc", icon: "users" },
    { label: "Cần làm hàng", href: "#/nhu-cau", icon: "chart" },
    { label: "Chuyển kho", href: "#/chuyen-kho", icon: "truck" },
    { label: "Sản phẩm", href: "#/san-pham", icon: "tag" },
    { label: "Vị trí kho", href: "#/vi-tri", icon: "box" },
    { label: "Số thùng", href: "#/so-thung", icon: "grid" },
  ] },
  { title: "Sản xuất", icon: "factory", items: [
    { label: "Phiếu sản xuất", href: "#/san_xuat", icon: "factory" },
    { label: "Dashboard SX", href: "#/sx-bang", icon: "chart" },
    { label: "Danh sách thợ", href: "#/tho", icon: "users" },
    { label: "Tiền công thợ", href: "#/tien-cong", icon: "wallet", office: true },
    { label: "Báo cáo sản xuất", href: "#/bao-cao", icon: "receipt", office: true },
    { label: "Lương sản phẩm", href: "#/luong-sp", icon: "wallet", office: true },
  ] },
  { title: "Tài chính", icon: "wallet", items: [
    { label: "Sổ quỹ", href: "#/quy", icon: "wallet" },
    { label: "Bảng giá", href: "#/bang-gia", icon: "receipt" },
  ] },
  { title: "Hình ảnh", icon: "camera", items: [
    { label: "Camera 2026", href: "#/camera", icon: "camera" },
  ] },
  { title: "Hệ thống", icon: "settings", items: [
    { label: "Lịch sử thao tác", href: "#/lich-su", icon: "history" },
    { label: "Thống kê sử dụng", href: "#/usage", icon: "chart", admin: true },
    { label: "Cài đặt", href: "#/login", icon: "settings" },
    { label: "Quản lý user", href: "#/users", icon: "lock", admin: true },
  ] },
];

export function Home() {
  const role = currentUser()?.role;
  const office = role === "admin" || role === "van_phong";
  const admin = role === "admin";
  return (
    <div class="home">
      {GROUPS.map((g) => {
        const items = g.items.filter((it) => (!it.office || office) && (!it.admin || admin));
        if (!items.length) return null;
        return (
          <section class="home-grp" key={g.title}>
            <div class="home-grp-h"><Icon name={g.icon} size={15} /> {g.title}</div>
            <div class="home-grid">
              {items.map((it) => (
                <a class="home-tile" href={it.href} key={it.href}>
                  <span class="home-tile-ic"><Icon name={it.icon} size={22} /></span>
                  <span class="home-tile-lb">{it.label}</span>
                </a>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
