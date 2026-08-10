// DANH MỤC MENU "☰ Thêm" — nguồn DUY NHẤT của các mục trong trang #/home.
// Tách khỏi pages/Home.tsx để recent.ts (mục gần đây) dùng lại được mà không phải
// import cả trang. Thêm tính năng mới = thêm 1 dòng vào GROUPS.
// Mục theo quyền: office = admin/van_phong, admin = admin.

export type MenuItem = { label: string; href: string; icon: string; office?: boolean; admin?: boolean };
export type MenuGroup = { title: string; icon: string; items: MenuItem[] };

export const GROUPS: MenuGroup[] = [
  { title: "Đơn hàng", icon: "clipboard", items: [
    { label: "Đơn hàng", href: "#/orders", icon: "clipboard" },
    { label: "Tạo đơn", href: "#/create", icon: "plus" },
    { label: "Khách hàng", href: "#/customers", icon: "user" },
    { label: "Trả hàng", href: "#/tra-hang", icon: "refresh" },
    { label: "Lịch giao", href: "#/lich", icon: "calendar" },
    { label: "Đang giao", href: "#/dang-giao", icon: "truck" },
    { label: "Nộp tiền", href: "#/nop-tien", icon: "banknote" },
    { label: "Nhận tiền", href: "#/nhan-tien", icon: "wallet", office: true },
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
    // Ẩn "Hao hụt NL phụ" (đối chiếu theo CÔNG THỨC, dễ nhầm với kiểm kho thường).
    // Route + API + code còn nguyên (deep-link #/hao-hut-nl vẫn mở) — bật lại khi cần.
    // { label: "Hao hụt NL phụ", href: "#/hao-hut-nl", icon: "chart", office: true },
    { label: "Sản phẩm", href: "#/san-pham", icon: "tag" },
    { label: "Vị trí kho", href: "#/vi-tri", icon: "box" },
    { label: "Số thùng", href: "#/so-thung", icon: "grid" },
    // Kho ĐẬU = hệ kho RIÊNG (hàng hoá riêng, vị trí riêng, phiếu riêng) nhưng ở
    // menu chỉ MỘT mục — mọi thứ còn lại (phiếu, nhập, xuất, thiết lập) vào từ
    // chính trang #/kho-dau.
    { label: "Kho đậu", href: "#/kho-dau", icon: "box" },
  ] },
  { title: "Sản xuất", icon: "factory", items: [
    { label: "Phiếu sản xuất", href: "#/san_xuat", icon: "factory" },
    { label: "Dashboard SX", href: "#/sx-bang", icon: "chart" },
    { label: "Danh sách thợ", href: "#/tho", icon: "users" },
    { label: "Vệ sinh khu vực", href: "#/khu-vuc", icon: "leaf" },
    { label: "Chất lượng mâm kẹo", href: "#/chat-luong", icon: "star" },
  ] },
  { title: "Lương", icon: "wallet", items: [
    { label: "Bảng lương tháng", href: "#/luong-thang", icon: "wallet", office: true },
    { label: "Lương SP theo ngày", href: "#/luong-ngay", icon: "grid", office: true },
    { label: "Chấm công", href: "#/cham-cong", icon: "clock" },
    { label: "Nhập ứng lương", href: "#/nhap-ung", icon: "banknote", office: true },
    { label: "Nhập phụ cấp", href: "#/nhap-phu-cap", icon: "banknote", office: true },
    { label: "Tiền công thợ", href: "#/tien-cong", icon: "wallet", office: true },
    { label: "In phiếu lương", href: "#/in-luong", icon: "printer", office: true },
    { label: "Báo cáo sản xuất", href: "#/bao-cao", icon: "receipt", office: true },
    { label: "Lương sản phẩm", href: "#/luong-sp", icon: "wallet", office: true },
  ] },
  { title: "Tài chính", icon: "wallet", items: [
    { label: "Nợ quá hạn", href: "#/no-qua-han", icon: "clock", office: true },
    { label: "Thu tiền nhanh", href: "#/thu-tien-nhanh", icon: "zap", office: true },
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

/** Mọi mục, phẳng — kèm tên nhóm để hiện/tìm kiếm. */
export const ALL_ITEMS: (MenuItem & { group: string })[] =
  GROUPS.flatMap((g) => g.items.map((it) => ({ ...it, group: g.title })));

/** User (theo role) được thấy mục này không? */
export function itemAllowed(it: MenuItem, office: boolean, admin: boolean): boolean {
  return (!it.office || office) && (!it.admin || admin);
}

/** Route của mục có khớp trang đang mở không? Khớp khi BẰNG hoặc là đoạn CHA
 *  (`#/kho` khớp `#/kho/K10` nhưng KHÔNG khớp `#/kho-dau`, `#/tho` không nuốt
 *  `#/thung`) — cùng luật với guides/types.ts::routeMatches. */
function routeMatches(route: string, hash: string): boolean {
  return hash === route || hash.startsWith(route + "/");
}

/** Trang đang mở thuộc mục nào trong menu? Lấy route DÀI NHẤT khớp (cụ thể nhất),
 *  null nếu không thuộc mục nào (vd trang chi tiết đơn #/order/123). */
export function findMenuItem(rawHash: string): MenuItem | null {
  const hash = (rawHash || "").split("?")[0].trim();
  if (!hash || hash === "#" || hash === "#/") return null;
  let best: MenuItem | null = null;
  for (const it of ALL_ITEMS) {
    const route = it.href.split("?")[0];
    if (routeMatches(route, hash) && (!best || route.length > best.href.split("?")[0].length)) {
      best = it;
    }
  }
  return best;
}
