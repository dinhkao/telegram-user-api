// Trang chủ (#/home) — mọi mục của app gom theo NHÓM liên quan, mỗi mục 1 ô bấm được.
// Thay menu "Mục khác" dài (bị cắt) bằng trang cuộn được, có phân nhóm. Vào từ nút ☰
// Thêm ở thanh điều hướng. Mục theo quyền: office = admin/van_phong, admin = admin.
import { useState } from "preact/hooks";
import { currentUser } from "../api";
import { foldVN } from "../format";
import { Icon } from "../ui/Icon";
import { SearchBar } from "../ui/SearchBar";

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
    { label: "Xuất hủy", href: "#/xuat-huy", icon: "trash" },
    { label: "Điều chỉnh tồn", href: "#/dieu-chinh", icon: "edit" },
    { label: "Hao hụt NL phụ", href: "#/hao-hut-nl", icon: "chart", office: true },
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
    { label: "Thu tiền", href: "#/thu-tien", icon: "banknote", office: true },
    { label: "Sổ quỹ", href: "#/quy", icon: "wallet" },
    { label: "Két tiền", href: "#/ket", icon: "wallet" },
    { label: "Bảng giá", href: "#/bang-gia", icon: "receipt" },
  ] },
  { title: "Hình ảnh", icon: "camera", items: [
    { label: "Camera 2026", href: "#/camera", icon: "camera", office: true },
  ] },
  { title: "Hệ thống", icon: "settings", items: [
    { label: "Hướng dẫn", href: "#/huong-dan", icon: "info" },
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
  const [query, setQuery] = useState("");
  const normalizedQuery = foldVN(query.trim());
  const visibleGroups = GROUPS.map((g) => {
    const allowedItems = g.items.filter((it) => (!it.office || office) && (!it.admin || admin));
    const items = normalizedQuery
      ? allowedItems.filter((it) => foldVN(`${it.label} ${g.title}`).includes(normalizedQuery))
      : allowedItems;
    return { ...g, items };
  }).filter((g) => g.items.length > 0);

  return (
    <div class="home">
      <div class="home-search">
        <SearchBar value={query} onInput={setQuery} placeholder="Tìm trong menu Thêm…" />
      </div>
      {visibleGroups.map((g) => {
        return (
          <section class="home-grp" key={g.title}>
            <div class="home-grp-h"><Icon name={g.icon} size={15} /> {g.title}</div>
            <div class="home-grid">
              {g.items.map((it) => (
                <a class="home-tile" href={it.href} key={it.href}>
                  <span class="home-tile-ic"><Icon name={it.icon} size={22} /></span>
                  <span class="home-tile-lb">{it.label}</span>
                </a>
              ))}
            </div>
          </section>
        );
      })}
      {!visibleGroups.length && (
        <div class="home-empty">
          <Icon name="search" size={24} />
          <span>Không tìm thấy mục phù hợp</span>
          <button class="btn small" onClick={() => setQuery("")}>Xoá tìm kiếm</button>
        </div>
      )}
    </div>
  );
}
