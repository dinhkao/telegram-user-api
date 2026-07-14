// Kiểu dữ liệu HƯỚNG DẪN + hàm khớp bài theo trang đang xem.
// Nội dung guide là HTML TĨNH (do ta viết, an toàn) — render qua dangerouslySetInnerHTML
// ở pages/Guides.tsx. Nối: guides/registry.ts (gom bài), HelpFab (truyền ?from).

export type GuideSection = { title: string; html: string };

export type Guide = {
  key: string;          // slug URL: #/huong-dan/:key
  icon: string;         // tên ui/Icon
  title: string;
  desc: string;         // 1 dòng mô tả ở danh sách
  cat: string;          // mục để nhóm ở danh sách
  routes: string[];     // các hash-prefix trang mà bài này liên quan (vd "#/ket")
  sections: GuideSection[];
};

// Thứ tự các mục hiển thị ở trang danh sách.
export const GUIDE_CATS = [
  "Đơn hàng & khách",
  "Kho & hàng hoá",
  "Sản xuất",
  "Tài chính",
  "Khác & hệ thống",
];

// Chuẩn hoá hash trang hiện tại về dạng so khớp: bỏ query (?...), coi trang chủ/rỗng
// là danh sách đơn.
export function normalizeFrom(rawHash: string | null | undefined): string {
  let h = (rawHash || "").split("?")[0].trim();
  if (h === "" || h === "#" || h === "#/") h = "#/orders";
  return h;
}

// 1 route-prefix có khớp trang `from` không? Khớp khi bằng đúng hoặc là đoạn cha
// (from bắt đầu bằng route + "/") — tránh khớp nhầm tiền tố (vd "#/kho" ≠ "#/khach").
function routeMatches(route: string, from: string): boolean {
  return from === route || from.startsWith(route + "/");
}

// Trả về các bài liên quan trang `from` (đã chuẩn hoá). Ưu tiên route DÀI nhất khớp
// (cụ thể hơn), nhưng vẫn gộp mọi bài có bất kỳ route khớp.
export function guidesForRoute(guides: Guide[], rawHash: string): Guide[] {
  const from = normalizeFrom(rawHash);
  const scored: { g: Guide; len: number }[] = [];
  for (const g of guides) {
    let best = -1;
    for (const r of g.routes) {
      if (routeMatches(r, from)) best = Math.max(best, r.length);
    }
    if (best >= 0) scored.push({ g, len: best });
  }
  scored.sort((a, b) => b.len - a.len);
  return scored.map((s) => s.g);
}
